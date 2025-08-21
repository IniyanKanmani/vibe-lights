import asyncio
import multiprocessing
import os
import queue
import threading
from json import dumps, loads
from multiprocessing.connection import Connection
from typing import List

import websockets


class HomeAssistantWebSocketProcess(multiprocessing.Process):
    def __init__(
        self, process_con: Connection, process_queue: multiprocessing.Queue
    ) -> None:
        super().__init__()

        self.__process_con = process_con
        self.__process_queue = process_queue

        self.__base_url = f"ws://{os.getenv("HOMEASSISTANT_SERVER_IP")}:{os.getenv("HOMEASSISTANT_SERVER_PORT")}/api/websocket"
        self.__api_key = os.getenv("HOMEASSISTANT_API_KEY")

        self.__connection_status = False
        self.__id = 1

    def __initialize_loop(self):
        self.__loop = asyncio.new_event_loop()
        threading.Thread(target=self.__loop_runner, daemon=True).start()

    def __loop_runner(self):
        asyncio.set_event_loop(self.__loop)
        self.__loop.run_forever()

    def __is_connected(self) -> bool:
        return self.__connection_status

    async def __connect(self) -> None:
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
        initial_light_states = {}

        for state in states:
            initial_light_states[state["entity_id"]] = {
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

        self.__initial_light_states = initial_light_states

        print(initial_light_states)

    async def __fetch_light_states(self) -> None:
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

        print(self.__lights, end="\n\n")

    async def __fetch_light_actions(self) -> None:
        await self.__ha_socket.send(dumps({"id": self.__id, "type": "get_services"}))
        self.__id += 1

        actions = loads(await self.__ha_socket.recv())["result"]
        actions = {"light": actions["light"]}

        # with open("actions.json", "w") as f:
        #     f.write(dumps(actions))

    # async def __listen(self) -> None:
    #     async for event in self.__ha_socket:
    #         print(loads(event))

    async def __send_light_state(self, brightness: int, rgb_color: List[int]) -> None:
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

    async def __recover_initial_state(self) -> None:
        messages = []
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
                messages.append(self.__ha_socket.send(data))

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
                messages.append(self.__ha_socket.send(data))

        await asyncio.gather(*messages)

        print("Initial State Restored")

    def __push_states(self) -> None:
        while True:
            try:
                br, cl = self.__process_queue.get(timeout=3)
                print(f"Br: {br}, R: {cl[0]}, G: {cl[1]}, B: {cl[2]}")

                self.__loop.call_soon_threadsafe(
                    asyncio.create_task, self.__send_light_state(br, cl)
                )
            except queue.Empty:
                print("Queue Empty")
            finally:
                if not self.__connection_status:
                    print("Queue Closed")
                    break

    async def __close_socket(self) -> None:
        await self.__ha_socket.close()
        self.__connection_status = False

        print("Web Socket Closed")

    def __process_connection_listener(self):
        while True:
            message = self.__process_con.recv()

            if message == "kill":
                self.kill()
                self.close()

                break

    def run(self) -> None:
        self.__initialize_loop()

        asyncio.run_coroutine_threadsafe(self.__connect(), self.__loop).result()

        if not self.__is_connected():
            print("Websocket: Auth Invalid")

            return

        asyncio.run_coroutine_threadsafe(
            self.__fetch_light_states(), self.__loop
        ).result()
        asyncio.run_coroutine_threadsafe(
            self.__fetch_light_actions(), self.__loop
        ).result()

        threading.Thread(target=self.__process_connection_listener, daemon=True).start()

        # self.__listener_task = self.__loop.create_task(self.__listen())

        self.__push_states()

    def kill(self) -> None:
        # self.__listener_task.cancel()

        asyncio.run_coroutine_threadsafe(
            self.__recover_initial_state(), self.__loop
        ).result()
        asyncio.run_coroutine_threadsafe(self.__close_socket(), self.__loop).result()

        self.__loop.stop()

        print("Web Socket Process Killed")
