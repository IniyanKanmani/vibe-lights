"""
Home Assistant WebSocket backend process for controlling smart lights.

This module provides a multiprocessing-based backend that communicates with
Home Assistant via its WebSocket API for real-time light control with lower
latency than the REST API backend.
"""

import asyncio
import multiprocessing
import os
import queue
import threading
from json import dumps, loads
from multiprocessing.connection import Connection
from time import sleep
from typing import List

import websockets
from loguru import logger


class HomeAssistantWebSocketProcess(multiprocessing.Process):
    """
    Process for controlling Home Assistant lights via WebSocket API.

    This class runs as a separate process and handles communication with
    Home Assistant's WebSocket API to control smart lights with lower
    latency than REST API. It maintains the initial state of lights
    and restores them when the process terminates.
    """

    def __init__(
        self, process_connection: Connection, process_queue: multiprocessing.Queue
    ) -> None:
        """
        Initialize the Home Assistant WebSocket process.

        Args:
            process_connection (Connection): Pipe connection for receiving control signals.
            process_queue (multiprocessing.Queue): Queue for receiving light state updates
                as tuples of (brightness, r, g, b).
        """
        super().__init__()

        logger.debug("Connection Backend: WebSocket")

        self.__process_connection = process_connection
        self.__process_queue = process_queue

        self.__base_url = f"ws://{os.getenv('HOMEASSISTANT_SERVER_IP')}:{os.getenv('HOMEASSISTANT_SERVER_PORT')}/api/websocket"
        self.__api_key = os.getenv("HOMEASSISTANT_API_KEY")

        self.__connection_status = False
        self.__id = 1

    def __initialize_loop(self) -> None:
        """
        Initialize the asyncio event loop in a separate thread.
        """
        self.__loop = asyncio.new_event_loop()
        threading.Thread(target=self.__loop_runner, daemon=True).start()

    def __loop_runner(self) -> None:
        """
        Run the asyncio event loop forever.
        """
        asyncio.set_event_loop(self.__loop)
        self.__loop.run_forever()

    async def __connect(self) -> None:
        """
        Establish WebSocket connection to Home Assistant and authenticate.

        Raises:
            Exception: If connection times out or authentication fails.
        """
        self.__ha_socket = await websockets.connect(
            self.__base_url,
            open_timeout=1,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=1,
        )

        try:
            message = loads(await self.__ha_socket.recv())
        except Exception:
            raise Exception("Connection Timeout")

        if message["type"] == "auth_required":
            await self.__ha_socket.send(
                dumps({"type": "auth", "access_token": self.__api_key})
            )

        try:
            message = loads(await self.__ha_socket.recv())
        except Exception:
            raise Exception("Connection Timeout")

        if message["type"] == "auth_ok":
            self.__connection_status = True
        elif message["type"] == "auth_invalid":
            self.__connection_status = False

    def __store_initial_light_states(self, states: List[dict]) -> None:
        """
        Store the initial state of all lights for later restoration.

        Args:
            states (List[dict]): List of light state dictionaries from Home Assistant.
        """
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
        """
        Fetch current light states from Home Assistant via WebSocket.
        """
        await self.__ha_socket.send(dumps({"id": self.__id, "type": "get_states"}))
        self.__id += 1

        message = loads(await self.__ha_socket.recv())["result"]
        states = list(
            filter(lambda x: str(x["entity_id"]).startswith("light"), message)
        )

        self.__store_initial_light_states(states)
        self.__lights = list(self.__initial_light_states.keys())

        logger.info(f"Lights: {self.__lights}")

    async def __send_light_state(self, br: int, r: int, g: int, b: int) -> None:
        """
        Send light state update to Home Assistant via WebSocket.

        Args:
            br (int): Brightness value (0-255).
            r (int): Red color value (0-255).
            g (int): Green color value (0-255).
            b (int): Blue color value (0-255).
        """
        data = dumps(
            {
                "id": self.__id,
                "type": "call_service",
                "domain": "light",
                "service": "turn_on",
                "service_data": {"brightness": br, "rgb_color": [r, g, b]},
                "target": {"entity_id": self.__lights},
                "return_response": False,
            }
        )
        self.__id += 1

        await self.__ha_socket.send(data)

    def __push_states(self) -> None:
        """
        Continuously push light states from queue to Home Assistant.
        """
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

    async def __recover_initial_state(self) -> None:
        """
        Restore all lights to their initial states.
        """
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

        logger.debug("Initial State Restored")

    async def __close_socket(self) -> None:
        """
        Close the WebSocket connection.
        """
        await self.__ha_socket.close()
        self.__connection_status = False

        logger.debug("Web Socket Connection Closed")

    def __send_ready_signal(self) -> None:
        """
        Send ready signal to the main process.
        """
        self.__process_connection.send("ready")

    def __process_connection_listener(self) -> None:
        """
        Listen for control signals from the main process.
        """
        while True:
            message = self.__process_connection.recv()

            if message == "kill":
                break

        self.kill()
        self.close()

    def run(self) -> None:
        """
        Main process execution loop.

        Raises:
            Exception: If authentication fails.
        """
        try:
            self.__initialize_loop()
            asyncio.run_coroutine_threadsafe(self.__connect(), self.__loop).result()

            if not self.__connection_status:
                raise Exception("Websocket: Auth Invalid")

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
        """
        Kill the process and restore initial light states.
        """
        sleep(0.3)
        asyncio.run_coroutine_threadsafe(
            self.__recover_initial_state(),
            self.__loop,
        ).result()

        sleep(0.3)
        asyncio.run_coroutine_threadsafe(
            self.__close_socket(),
            self.__loop,
        ).result()

        self.__loop.stop()

        logger.debug("Web Socket Process Killed")
