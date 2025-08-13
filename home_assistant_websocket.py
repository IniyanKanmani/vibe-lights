import os
from json import dumps, loads

import websockets


class HomeAssistantWebSocket:
    def __init__(self):
        self.base_url = f"ws://{os.getenv("HOMEASSISTANT_SERVER_IP")}:{os.getenv("HOMEASSISTANT_SERVER_PORT")}/api/websocket"
        self.api_key = os.getenv("HOMEASSISTANT_API_KEY")
        self.id = 1

    async def connect(self):
        self.ha_socket = await websockets.connect(self.base_url)

        message = loads(await self.ha_socket.recv())

        if message["type"] == "auth_required":
            await self.ha_socket.send(
                dumps({"type": "auth", "access_token": self.api_key})
            )

        message = loads(await self.ha_socket.recv())

        if message["type"] == "auth_ok":
            return True
        elif message["type"] == "auth_invalid":
            return False

    async def listen_for_messages(self):
        async for event in self.ha_socket:
            print(loads(event))

    async def fetch_light_actions(self):
        await self.ha_socket.send(dumps({"id": self.id, "type": "get_services"}))
        self.id += 1

        actions = loads(await self.ha_socket.recv())["result"]
        with open("output.txt", "w") as f:
            f.write(dumps(actions))

    async def fetch_all_lights(self):
        await self.ha_socket.send(dumps({"id": self.id, "type": "get_states"}))
        self.id += 1

        states = loads(await self.ha_socket.recv())["result"]
        states = filter(lambda x: str(x["entity_id"]).startswith("light"), states)
        states = map(lambda x: x["entity_id"], states)

        self.lights = list(states)
        print(self.lights)

    async def turn_on_lights(self):
        data = dumps(
            {
                "id": self.id,
                "type": "call_service",
                "domain": "light",
                "service": "turn_on",
                "service_data": {"color_temp_kelvin": 6500, "brightness_pct": 100},
                "target": {"entity_id": self.lights},
                "return_response": False,
            }
        )
        self.id += 1

        await self.ha_socket.send(data)

    async def set_light_color(self, color):
        data = dumps(
            {
                "id": self.id,
                "type": "call_service",
                "domain": "light",
                "service": "turn_on",
                "service_data": {"rgb_color": color},
                "target": {"entity_id": self.lights},
                "return_response": False,
            }
        )
        self.id += 1

        await self.ha_socket.send(data)

    async def turn_off_lights(self):
        data = dumps(
            {
                "id": self.id,
                "type": "call_service",
                "domain": "light",
                "service": "turn_off",
                "target": {"entity_id": self.lights},
                "return_response": False,
            }
        )
        self.id += 1

        await self.ha_socket.send(data)

    async def close_socket(self):
        await self.ha_socket.close()
