import os
from json import dumps, loads

import websockets


class HomeAssistantWebSocket:
    def __init__(self):
        home_assistant_server_ip = os.getenv("HOMEASSISTANT_SERVER_IP")
        home_assistant_server_port = os.getenv("HOMEASSISTANT_SERVER_PORT")

        self.base_url = f"ws://{home_assistant_server_ip}:{home_assistant_server_port}/api/websocket"
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

    async def fetch_light_states(self):
        await self.ha_socket.send(dumps({"id": self.id, "type": "get_states"}))
        self.id += 1

        states = loads(await self.ha_socket.recv())["result"]
        states = list(filter(lambda x: str(x["entity_id"]).startswith("light"), states))

        # with open("states.json", "w") as f:
        #     f.write(dumps(list(states)))

        self.lights = list(map(lambda x: x["entity_id"], states))

        print(self.lights)

    async def fetch_light_actions(self):
        await self.ha_socket.send(dumps({"id": self.id, "type": "get_services"}))
        self.id += 1

        actions = loads(await self.ha_socket.recv())["result"]
        actions = {"light": actions["light"]}

        # with open("actions.json", "w") as f:
        #     f.write(dumps(actions))

    async def listen(self):
        async for event in self.ha_socket:
            print(loads(event))

    async def send_light_state(self, brightness, color):
        data = dumps(
            {
                "id": self.id,
                "type": "call_service",
                "domain": "light",
                "service": "turn_on",
                "service_data": {"brightness": brightness, "rgb_color": color},
                "target": {"entity_id": self.lights},
                "return_response": False,
            }
        )
        self.id += 1

        await self.ha_socket.send(data)

    async def close_socket(self):
        await self.ha_socket.close()
