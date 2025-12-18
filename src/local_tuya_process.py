"""
Local Tuya backend process for controlling Tuya smart lights directly.

This module provides a multiprocessing-based backend that communicates directly
with Tuya smart lights on the local network using the TinyTuya library, bypassing
the cloud for the lowest latency control.
"""

import multiprocessing
import os
import queue
import sys
import threading
from json import dumps, loads
from multiprocessing.connection import Connection
from time import sleep
from typing import List

from loguru import logger
from tinytuya import BulbDevice, scanner, wizard


class LocalTuyaProcess(multiprocessing.Process):
    """
    Process for controlling Tuya lights directly on the local network.

    This class runs as a separate process and handles direct communication
    with Tuya smart lights using the TinyTuya library. It discovers devices,
    stores their initial states, and controls them in music mode for synchronized
    lighting effects.
    """

    def __init__(
        self, process_connection: Connection, process_queue: multiprocessing.Queue
    ) -> None:
        """
        Initialize the Local Tuya process.

        Args:
            process_connection (Connection): Pipe connection for receiving control signals.
            process_queue (multiprocessing.Queue): Queue for receiving light state updates
                as tuples of (brightness, r, g, b).
        """
        super().__init__()

        logger.debug("Connection Backend: LocalTuya")

        scanner.SCANTIME = 30  # just for the tinytuya.scanner module

        self.__process_connection = process_connection
        self.__process_queue = process_queue

        self.__connection_status = False

    def __initialize(self) -> None:
        """
        Initialize the process and discover Tuya devices.
        """
        logger.remove(0)
        logger.add(sys.stderr, level=str(os.getenv("LOG_LEVEL") or "INFO"))

        if not os.path.exists("devices.json"):
            config = {
                "apiKey": os.getenv("TUYA_API_KEY"),
                "apiSecret": os.getenv("TUYA_API_SECRET"),
                "apiRegion": os.getenv("TUYA_API_REGION"),
                "apiDeviceID": "scan",
            }

            with open("tinytuya.json", "w") as f:
                f.write(dumps(config, indent=2))

            wizard.wizard(
                assume_yes=True,
                skip_poll=False,
            )

        with open("devices.json", "r") as f:
            devs = loads(f.read())

            devices = []
            for dev in devs:
                if dev["category"] != "dj":
                    continue

                if "music" not in dev["mapping"]["21"]["values"]["range"]:
                    continue

                data = {
                    "id": dev["id"],
                    "name": dev["name"],
                    "ip_address": dev["ip"],
                    "local_key": dev["key"],
                    "category": dev["category"],
                    "version": dev["version"],
                }

                devices.append(data)

        self.__devices = devices

    def __connect(self) -> None:
        """
        Connect to all discovered Tuya devices.
        """
        self.__lights = []
        self.__initial_light_states = {}
        self.__light_devices: List[BulbDevice] = []

        for device in self.__devices:
            light = BulbDevice(
                dev_id=device["id"],
                address=device["ip_address"],
                local_key=device["local_key"],
                version=device["version"],
                persist=True,
            )

            self.__lights.append(device["name"])
            self.__light_devices.append(light)

            status = light.status()
            self.__initial_light_states[device["id"]] = status["dps"]

            light.set_mode("music", nowait=False)

        self.__connection_status = True

        logger.info(f"Lights: {self.__lights}")

    def __worker_threads_creator(self) -> None:
        """
        Create worker threads for each light device.
        """
        self.__is_thread_kill_recieved = False
        self.__light_state_queues = [queue.Queue()] * len(self.__lights)

        for i, q in enumerate(self.__light_state_queues):
            threading.Thread(
                target=self.__light_device_thread_executor,
                args=(q, self.__light_devices[i]),
            ).start()

    def __light_device_thread_executor(
        self, q: queue.Queue, device: BulbDevice
    ) -> None:
        """
        Execute light state updates for a specific device.

        Args:
            q (queue.Queue): Queue for state updates for this device.
            device (BulbDevice): The BulbDevice instance to control.
        """
        while True:
            try:
                msg = q.get(timeout=1)
                device.set_value(msg[0], msg[1], nowait=True)

                while q.qsize() > 0:
                    q.get_nowait()

            except queue.Empty:
                if not self.__is_thread_kill_recieved:
                    continue
                else:
                    break

    def __light_states_listener(self) -> None:
        """
        Listen for light state updates from the main process.
        """
        while True:
            try:
                br, r, g, b = self.__process_queue.get(timeout=1)
                self.__light_state_converter(br, r, g, b)

                logger.debug(f"Br: {br}, R: {r}, G: {g}, B: {b}")

                while self.__process_queue.qsize() > 0:
                    self.__process_queue.get_nowait()

            except queue.Empty:
                if self.__connection_status:
                    logger.debug("Queue Empty")
                else:
                    break

    def __light_state_converter(self, br: int, r: int, g: int, b: int) -> None:
        """
        Convert RGB/brightness values to Tuya music mode format.

        Args:
            br (int): Brightness value (0-255).
            r (int): Red color value (0-255).
            g (int): Green color value (0-255).
            b (int): Blue color value (0-255).
        """
        # Order: transition, r, g, b, colortemp, brightness
        # Hex Format: 011112222333344445555
        hex = ""
        hex += "%x" % 0
        hex += BulbDevice.rgb_to_hexvalue(r, g, b, "hsv16")
        hex += "%04x" % 0
        hex += "%04x" % int(1000 * (br / 255))

        for q in self.__light_state_queues:
            q.put_nowait(("27", hex))

    def __recover_light_state(self) -> None:
        """
        Restore all lights to their initial states.
        """
        for device in self.__light_devices:
            data = self.__initial_light_states[device.id]
            device.set_multiple_values(data, nowait=False)

        logger.debug("Initial State Restored")

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

        self.__is_thread_kill_recieved = True

        self.kill()
        self.close()

    def run(self) -> None:
        """
        Main process execution loop.
        """
        try:
            self.__initialize()
            self.__connect()

            threading.Thread(
                target=self.__process_connection_listener,
            ).start()

            self.__worker_threads_creator()
            self.__send_ready_signal()

            self.__light_states_listener()
        except KeyboardInterrupt:
            pass

    def __close_connection(self) -> None:
        """
        Close all device connections.
        """
        for device in self.__light_devices:
            device.close()

        self.__connection_status = False

        logger.debug("Local Tuya Connection Closed")

    def kill(self) -> None:
        """
        Kill the process and restore initial light states.
        """
        sleep(0.3)
        self.__recover_light_state()

        sleep(0.3)
        self.__close_connection()

        logger.debug("Local Tuya Process Finished")
