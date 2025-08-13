import asyncio
import os
from time import sleep

from dotenv import load_dotenv

from home_assistant_rest_api import HomeAssistantRestAPI
from home_assistant_websocket import HomeAssistantWebSocket
from basic_audio_manager import BasicAudioManager


async def main():
    load_dotenv()
    backend = os.getenv("BACKEND")

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
        is_connected = await ha_websocket.connect()

        if not is_connected:
            print("Websocket: Auth Invalid")

            return

        await ha_websocket.fetch_light_actions()
        await ha_websocket.fetch_all_lights()
        asyncio.create_task(ha_websocket.listen_for_messages())

        await ha_websocket.turn_on_lights()
        await asyncio.sleep(2)

        for _ in range(10):
            await ha_websocket.set_light_color([255, 255, 255])
            await asyncio.sleep(0.5)
            await ha_websocket.turn_off_lights()
            await asyncio.sleep(0.5)

        await ha_websocket.close_socket()


def sub_main():
    audio_manager = BasicAudioManager()
    audio_manager.define_io_devices()

    audio_manager.record_audio()
    sleep(1)
    audio_manager.play_audio()


if __name__ == "__main__":
    # asyncio.run(main())
    sub_main()
