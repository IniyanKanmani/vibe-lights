import multiprocessing
import os
import signal
import sys
from time import sleep
from typing import List

from dotenv import load_dotenv
from loguru import logger

from audio_input_stream_manager import AudioInputStreamManager
from home_assistant_rest_api_process import HomeAssistantRestAPIProcess
from home_assistant_websocket_process import HomeAssistantWebSocketProcess
from local_tuya_process import LocalTuyaProcess


def main() -> None:
    load_dotenv()

    logger.remove(0)
    logger.add(sys.stderr, level=str(os.getenv("LOG_LEVEL") or "DEBUG"))

    backend = str(os.getenv("BACKEND")).lower()

    server_con, client_con = multiprocessing.Pipe()
    process_queue = multiprocessing.Queue()

    audio_manager = AudioInputStreamManager()
    backend_process = None

    if backend == "restapi":
        backend_process = HomeAssistantRestAPIProcess(client_con, process_queue)

    elif backend == "websocket":
        backend_process = HomeAssistantWebSocketProcess(client_con, process_queue)

    elif backend == "localtuya":
        backend_process = LocalTuyaProcess(client_con, process_queue)

    else:
        raise ValueError("Invalid Backend")

    def callback(br: int, rgb_color: List[int]) -> None:
        process_queue.put_nowait((br, rgb_color))

    def finished_callback() -> None:
        server_con.send("kill")

    audio_manager.initialize_stream()
    audio_manager.build_stream(
        latency=85.34,
        callback=callback,
        finished_callback=finished_callback,
    )

    setup_cleanup(audio_manager)

    backend_process.start()

    if server_con.recv() == "ready":
        sleep(0.5)
        audio_manager.start_stream()


def setup_cleanup(
    audio_manager: AudioInputStreamManager,
) -> None:
    def cleanup_handler(*_) -> None:
        if audio_manager and audio_manager.is_stream_alive():
            audio_manager.close_stream()

    signal.signal(signal.SIGINT, cleanup_handler)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
