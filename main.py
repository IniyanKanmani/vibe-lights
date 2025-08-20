import asyncio
import multiprocessing
import os
from time import sleep
from typing import List

from dotenv import load_dotenv

from audio_input_stream_manager import AudioInputStreamManager
from home_assistant_rest_api import HomeAssistantRestAPI
from home_assistant_websocket_process import HomeAssistantWebSocketProcess


async def main():
    load_dotenv()
    backend = str(os.getenv("BACKEND")).lower()

    audio_manager = AudioInputStreamManager()
    audio_manager.initialize_input_device()

    if backend == "restapi":
        ha_rest_api = HomeAssistantRestAPI()
        ha_rest_api.fetch_all_lights()

        for _ in range(10):
            ha_rest_api.control_lights([255, 255, 255])
            sleep(0.5)
            ha_rest_api.turn_lights_off()
            sleep(0.5)

    elif backend == "websocket":
        process_queue = multiprocessing.Queue()
        ser_con, cli_con = multiprocessing.Pipe()

        ha_websocket_process = HomeAssistantWebSocketProcess(cli_con, process_queue)
        ha_websocket_process.start()

        def callback(br: int, cl: List[int]) -> None:
            process_queue.put_nowait((br, cl))

        def finished_callback() -> None:
            ser_con.send("kill")
            audio_manager.close()

        audio_manager.build_stream(
            ms=500,
            latency=None,
            callback=callback,
            finished_callback=finished_callback,
        )

    sleep(2)
    audio_manager.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting...")
