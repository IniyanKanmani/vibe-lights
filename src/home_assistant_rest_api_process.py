import asyncio
import multiprocessing
import os
import queue
import threading
from multiprocessing.connection import Connection
from time import sleep
from typing import List

import httpx
from loguru import logger


class HomeAssistantRestAPIProcess(multiprocessing.Process):
    def __init__(
        self, process_connection: Connection, process_queue: multiprocessing.Queue
    ) -> None:
        super().__init__()

        logger.debug("Connection Backend: RestAPI")

        self.__process_connection = process_connection
        self.__process_queue = process_queue

        self.__base_url = f"http://{os.getenv("HOMEASSISTANT_SERVER_IP")}:{os.getenv("HOMEASSISTANT_SERVER_PORT")}/api"
        self.__headers = {
            "Authorization": f"Bearer {os.getenv("HOMEASSISTANT_API_KEY")}",
            "content-type": "application/json",
        }

        self.__connection_status = False

    def __initialize_loop(self) -> None:
        self.__loop = asyncio.new_event_loop()
        threading.Thread(target=self.__loop_runner, daemon=True).start()

    def __loop_runner(self) -> None:
        asyncio.set_event_loop(self.__loop)
        self.__loop.run_forever()

    def __connect(self) -> None:
        self.__client_session = httpx.AsyncClient(
            base_url=self.__base_url,
            headers=self.__headers,
            timeout=10,
        )
        self.__connection_status = True

    def __store_initial_light_states(self, states: List[dict]) -> None:
        initial_light_states = {}

        for state in states:
            if state["state"] == "unavailable":
                continue

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

    async def __fetch_light_states(self) -> None:
        response = await self.__client_session.get(url="/states")
        states = response.json()

        states = list(filter(lambda x: str(x["entity_id"]).startswith("light"), states))

        self.__store_initial_light_states(states)
        self.__lights = list(map(lambda x: x["entity_id"], states))

        logger.info(f"Lights: {self.__lights}")

    async def __send_light_state(self, br: int, r: int, g: int, b: int) -> None:
        data = {
            "entity_id": self.__lights,
            "brightness": br,
            "rgb_color": [r, g, b],
        }

        try:
            await self.__client_session.post(
                url="/services/light/turn_on",
                json=data,
            )
        except httpx.TimeoutException:
            logger.debug("Timeout")
        except httpx.ReadError:
            logger.debug("ReadError")
        except httpx.RemoteProtocolError:
            logger.debug("RemoteProtocolError")

    def __push_states(self) -> None:
        while True:
            try:
                br, r, g, b = self.__process_queue.get(timeout=1)
                self.__loop.call_soon_threadsafe(
                    asyncio.create_task,
                    self.__send_light_state(br, r, g, b),
                )

                logger.debug(f"Br: {br}, R: {r}, G: {g}, B: {b}")

                while self.__process_queue.qsize() > 0:
                    self.__process_queue.get_nowait()

            except queue.Empty:
                if self.__connection_status:
                    logger.debug("Queue Empty")
                else:
                    break

    async def __recover_light_state(self) -> None:
        messages = []

        for light, state in self.__initial_light_states.items():
            if state["state"] == "off":
                data = {
                    "entity_id": light,
                }

                messages.append(
                    self.__client_session.post(
                        url="/services/light/turn_off",
                        json=data,
                    )
                )

            elif state["state"] == "on":
                attributes = state["attributes"]

                data = {"entity_id": light, **attributes}

                messages.append(
                    self.__client_session.post(
                        url="/services/light/turn_on",
                        json=data,
                    )
                )

        try:
            await asyncio.gather(*messages)
        except httpx.TimeoutException:
            logger.debug("Timeout")
        except httpx.ReadError:
            logger.debug("ReadError")
        except httpx.RemoteProtocolError:
            logger.debug("RemoteProtocolError")

        logger.debug("Initial State Restored")

    async def __close_connection(self) -> None:
        await self.__client_session.aclose()
        self.__connection_status = False

        logger.debug("Rest API Connection Closed")

    def __send_ready_signal(self) -> None:
        self.__process_connection.send("ready")

    def __process_connection_listener(self):
        while True:
            message = self.__process_connection.recv()

            if message == "kill":
                break

        self.kill()
        self.close()

    def run(self) -> None:
        try:
            self.__initialize_loop()
            self.__connect()

            asyncio.run_coroutine_threadsafe(
                self.__fetch_light_states(),
                self.__loop,
            ).result()

            threading.Thread(
                target=self.__process_connection_listener,
            ).start()

            self.__send_ready_signal()
            self.__push_states()
        except KeyboardInterrupt:
            pass

    def kill(self) -> None:
        sleep(0.3)
        asyncio.run_coroutine_threadsafe(
            self.__recover_light_state(),
            self.__loop,
        ).result()

        sleep(0.3)
        asyncio.run_coroutine_threadsafe(
            self.__close_connection(),
            self.__loop,
        ).result()

        self.__loop.stop()

        logger.debug("Rest API Process Killed")
