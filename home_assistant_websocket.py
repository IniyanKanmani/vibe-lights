import os
from json import dumps, loads
from typing import List

import websockets


class HomeAssistantWebSocket:
    def __init__(self) -> None:
        self.__base_url = f"ws://{os.getenv("HOMEASSISTANT_SERVER_IP")}:{os.getenv("HOMEASSISTANT_SERVER_PORT")}/api/websocket"
        self.__api_key = os.getenv("HOMEASSISTANT_API_KEY")
        self.__id = 1
        self.__connection_status = False

    def is_connected(self) -> bool:
        return self.__connection_status

    async def connect(self) -> None:
        self.__ha_socket = await websockets.connect(self.__base_url)

        try:
            message = loads(await self.__ha_socket.recv())
        except Exception:
            self.__connection_status = False
            print("Connection Timeout")

            return

        if message["type"] == "auth_required":
            await self.__ha_socket.send(
                dumps({"type": "auth", "access_token": self.__api_key})
            )

        try:
            message = loads(await self.__ha_socket.recv())
        except Exception:
            self.__connection_status = False
            print("Connection Timeout")

            return

        if message["type"] == "auth_ok":
            self.__connection_status = True
        elif message["type"] == "auth_invalid":
            self.__connection_status = False

    def __store_initial_light_states(self, states: List[dict]) -> None:
        self.__initial_light_states = {}

        for state in states:
            self.__initial_light_states[state["entity_id"]] = {
                "state": state["state"],
                "attributes": {
                    "effect": state["attributes"]["effect"],
                    "color_mode": state["attributes"]["color_mode"],
                    "brightness": state["attributes"]["brightness"],
                    "color_temp_kelvin": state["attributes"]["color_temp_kelvin"],
                    "color_temp": state["attributes"]["color_temp"],
                    "hs_color": state["attributes"]["hs_color"],
                    "rgb_color": state["attributes"]["rgb_color"],
                    "xy_color": state["attributes"]["xy_color"],
                    "raw_state": state["attributes"]["raw_state"],
                    "raw_color_mode": state["attributes"]["raw_color_mode"],
                    "raw_color": state["attributes"]["raw_color"],
                    "raw_brightness": state["attributes"]["raw_brightness"],
                    "raw_color_temp": state["attributes"]["raw_color_temp"],
                },
            }

    async def fetch_light_states(self) -> None:
        await self.__ha_socket.send(dumps({"id": self.__id, "type": "get_states"}))
        self.__id += 1

        message = loads(await self.__ha_socket.recv())["result"]
        states = list(
            filter(lambda x: str(x["entity_id"]).startswith("light"), message)
        )

        # with open("states.json", "w") as f:
        #     f.write(dumps(list(states)))

        self.__store_initial_light_states(states)
        self.__lights = list(map(lambda x: x["entity_id"], states))

        print(self.__lights)

    async def fetch_light_actions(self) -> None:
        await self.__ha_socket.send(dumps({"id": self.__id, "type": "get_services"}))
        self.__id += 1

        actions = loads(await self.__ha_socket.recv())["result"]
        actions = {"light": actions["light"]}

        # with open("actions.json", "w") as f:
        #     f.write(dumps(actions))

    async def listen(self) -> None:
        async for event in self.__ha_socket:
            print(loads(event))

    async def send_light_state(self, brightness: int, rgb_color: List[int]) -> None:
        data = dumps(
            {
                "id": self.__id,
                "type": "call_service",
                "domain": "light",
                "service": "turn_on",
                "service_data": {"brightness": brightness, "rgb_color": rgb_color},
                "target": {"entity_id": self.__lights},
                "return_response": False,
            }
        )
        self.__id += 1
        await self.__ha_socket.send(data)

    async def recover_initial_state(self) -> None:
        for light, state in self.__initial_light_states.items():
            if state["state"] == "off":
                data = dumps(
                    {
                        "id": self.__id,
                        "type": "call_service",
                        "domain": "light",
                        "service": "turn_off",
                        "target": {"entity_id": light},
                        "return_response": False,
                    }
                )
                self.__id += 1
                await self.__ha_socket.send(data)

            elif state["state"] == "on":
                attributes = state["attributes"]

                data = dumps(
                    {
                        "id": self.__id,
                        "type": "call_service",
                        "domain": "light",
                        "service": "turn_on",
                        "service_data": attributes,
                        "target": {"entity_id": light},
                        "return_response": False,
                    }
                )
                self.__id += 1
                await self.__ha_socket.send(data)

    async def close_socket(self) -> None:
        await self.__ha_socket.close()
        self.__connection_status = False
