import json
import os

from requests import get, post


class HomeAssistantRestAPI:
    def __init__(self):
        self.base_url = f"{str(os.getenv("HOMEASSISTANT_SERVER_URL")).rstrip("/")}/api"
        self.headers = {
            "Authorization": f"Bearer {os.getenv("HOMEASSISTANT_BEARER_TOKEN")}",
            "content-type": "application/json"
        }

    def fetch_all_lights(self):
        response = get(f"{self.base_url}/states", headers=self.headers)

        states = json.loads(response.text)
        states = filter(lambda x: str(x["entity_id"]).startswith("light"), states)
        states = map(lambda x: x["entity_id"], states)

        self.lights = list(states)

    def control_lights(self, color):
        for light in self.lights:
            data = {
                "entity_id": light,
                "rgb_color": color
            }

            post(
                f"{self.base_url}/services/light/turn_on",
                json=data,
                headers=self.headers
            )

    def turn_lights_off(self):
        for light in self.lights:
            data = {
                "entity_id": light,
            }

            post(
                f"{self.base_url}/services/light/turn_off",
                json=data,
                headers=self.headers
            )
