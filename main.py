import asyncio
import os
import queue
import signal
import sys
import threading
from time import sleep
from typing import List

from dotenv import load_dotenv

from audio_input_stream_manager import AudioInputStreamManager
from home_assistant_rest_api import HomeAssistantRestAPI
from home_assistant_websocket import HomeAssistantWebSocket
from websocket_queue_loop import WebsocketQueueLoop


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
        ha_websocket = HomeAssistantWebSocket()
        await ha_websocket.connect()

        if not ha_websocket.is_connected():
            print("Websocket: Auth Invalid")

            return

        await ha_websocket.fetch_light_states()
        await ha_websocket.fetch_light_actions()

        asyncio.create_task(ha_websocket.listen())

        # await ha_websocket.send_light_state(255, [255, 255, 255])
        # await asyncio.sleep(2)

        # for _ in range(10):
        #     await ha_websocket.send_light_state(255, [255, 255, 255])
        #     await asyncio.sleep(0.5)
        #     await ha_websocket.send_light_state(0, [255, 255, 255])
        #     await asyncio.sleep(0.5)

        light_data_queue = queue.Queue()

        websocket_queue_loop = WebsocketQueueLoop(light_data_queue, ha_websocket)
        websocket_queue_loop.initialize_loop()

        threading.Thread(target=websocket_queue_loop.push_states).start()

        def callback(br: int, cl: List[int]) -> None:
            light_data_queue.put_nowait((br, cl))

        def finished_callback() -> None:
            task = asyncio.create_task(ha_websocket.recover_initial_state())
            task.add_done_callback(
                lambda _: asyncio.create_task(ha_websocket.close_socket())
            )

        audio_manager.build_stream(
            ms=500,
            latency=None,
            callback=callback,
            finished_callback=finished_callback,
        )

        def sigint_handler(*_):
            audio_manager.close()
            sys.exit(0)

        signal.signal(signal.SIGINT, sigint_handler)

    audio_manager.start()


if __name__ == "__main__":
    asyncio.run(main())
