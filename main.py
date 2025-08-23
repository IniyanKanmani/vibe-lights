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


async def main() -> None:
    load_dotenv()
    backend = str(os.getenv("BACKEND")).lower()

    ser_con, cli_con = multiprocessing.Pipe()
    process_queue = multiprocessing.Queue()

    backend_process = None

    audio_manager = AudioInputStreamManager()
    audio_manager.initialize_input_device()

    if backend == "restapi":
        backend_process = HomeAssistantRestAPIProcess(cli_con, process_queue)

    elif backend == "websocket":
        backend_process = HomeAssistantWebSocketProcess(cli_con, process_queue)

    else:
        print("Invalid Backend")
        exit(1)

    def callback(br: int, cl: List[int]) -> None:
        process_queue.put_nowait((br, cl))

    def finished_callback() -> None:
        ser_con.send("kill")

    audio_manager.build_stream(
        ms=500,
        latency=None,
        callback=callback,
        finished_callback=finished_callback,
    )

    backend_process.start()
    sleep(2)
    threading.Thread(target=audio_manager.start, daemon=True).start()

    setup_cleanup(audio_manager, backend_process)


def setup_cleanup(
    audio_manager: AudioInputStreamManager, backend_process: multiprocessing.Process
) -> None:
    def cleanup(
        audio_manager: AudioInputStreamManager,
        ha_websocket_process: multiprocessing.Process,
    ) -> None:
        if audio_manager:
            audio_manager.close()
        if ha_websocket_process:
            ha_websocket_process.join()

    def signal_handler(*_) -> None:
        cleanup(audio_manager, backend_process)

    signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
