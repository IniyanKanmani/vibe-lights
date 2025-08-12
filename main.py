import os
from time import sleep

from dotenv import load_dotenv

from home_assistant_rest_api import HomeAssistantRestAPI


def main():
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


if __name__ == "__main__":
    main()
