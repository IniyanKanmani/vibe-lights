from time import sleep

from dotenv import load_dotenv

from home_assistant_rest_api import HomeAssistantRestAPI


def main():
    load_dotenv()

    ha_rest_api = HomeAssistantRestAPI()
    ha_rest_api.fetch_all_lights()

    ha_rest_api.control_lights([255, 255, 255])
    sleep(5)
    ha_rest_api.turn_lights_off()


if __name__ == "__main__":
    main()
