import asyncio
import multiprocessing
import os
import signal
import threading
from time import sleep
from typing import List

from dotenv import load_dotenv

from audio_input_stream_manager import AudioInputStreamManager
from home_assistant_rest_api_process import HomeAssistantRestAPIProcess
from home_assistant_websocket_process import HomeAssistantWebSocketProcess
from local_tuya_process import LocalTuyaProcess


async def main() -> None:
    load_dotenv()
    backend = str(os.getenv("BACKEND")).lower()

    audio_manager = AudioInputStreamManager()
    audio_manager_thread = None
    backend_process = None

    ser_con, cli_con = multiprocessing.Pipe()
    process_queue = multiprocessing.Queue()

    if backend == "rest_api":
        backend_process = HomeAssistantRestAPIProcess(cli_con, process_queue)

    elif backend == "web_socket":
        backend_process = HomeAssistantWebSocketProcess(cli_con, process_queue)

    elif backend == "tuya_local":
        backend_process = LocalTuyaProcess(cli_con, process_queue)

    else:
        raise Exception("Invalid Backend")

    def callback(br: int, cl: List[int]) -> None:
        process_queue.put_nowait((br, cl))

    def finished_callback() -> None:
        ser_con.send("kill")

    audio_manager.initialize_input_device()
    audio_manager.build_stream(
        ms=500,
        latency=None,
        callback=callback,
        finished_callback=finished_callback,
    )

    setup_cleanup(audio_manager, audio_manager_thread)

    backend_process.start()

    if ser_con.recv() == "ready":
        print("Ready Signal Received", end="\n\n")
        sleep(2)

        audio_manager_thread = threading.Thread(target=audio_manager.start, daemon=True)
        audio_manager_thread.start()


def setup_cleanup(
    audio_manager: AudioInputStreamManager,
    audio_manager_thread: threading.Thread | None,
) -> None:
    def cleanup_handler(*_) -> None:
        if audio_manager and audio_manager.stream.active:
            audio_manager.close()

        if audio_manager_thread and audio_manager_thread.is_alive():
            audio_manager_thread.join()

    signal.signal(signal.SIGINT, cleanup_handler)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
