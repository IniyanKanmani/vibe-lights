import multiprocessing
import os
import queue
import threading
from json import dumps, loads
from multiprocessing.connection import Connection
from time import sleep
from typing import List

from loguru import logger
from tinytuya import BulbDevice, scanner, wizard


class LocalTuyaProcess(multiprocessing.Process):
    def __init__(
        self, process_connection: Connection, process_queue: multiprocessing.Queue
    ) -> None:
        super().__init__()

        logger.debug("Connection Backend: LocalTuya")

        scanner.SCANTIME = 30  # just for the tinytuya.scanner module

        self.__process_connection = process_connection
        self.__process_queue = process_queue

        self.__connection_status = False

    def __initialize(self) -> None:
        if not os.path.exists("devices.json"):
            config = {
                "apiKey": os.getenv("TUYA_API_KEY"),
                "apiSecret": os.getenv("TUYA_API_SECRET"),
                "apiRegion": os.getenv("TUYA_API_REGION"),
                "apiDeviceID": "scan",
            }

            with open("tinytuya.json", "w") as f:
                f.write(dumps(config))

            wizard.wizard(
                assume_yes=True,
                skip_poll=False,
            )

        with open("devices.json", "r") as f:
            devices = loads(f.read())

            self.__devices = []
            for device in devices:
                if device["category"] != "dj":
                    continue

                if "music" not in device["mapping"]["21"]["values"]["range"]:
                    continue

                data = {
                    "id": device["id"],
                    "name": device["name"],
                    "ip_address": device["ip"],
                    "local_key": device["key"],
                    "category": device["category"],
                    "version": device["version"],
                }

                self.__devices.append(data)

    def __connect(self) -> None:
        self.__light_devices: List[BulbDevice] = []
        self.__initial_light_states = {}
        self.__same_value_max = None
        self.__lights = []

        light_value_max = None

        for device in self.__devices:
            if device["category"] != "dj":
                continue

            light = BulbDevice(
                dev_id=device["id"],
                address=device["ip_address"],
                local_key=device["local_key"],
                version=device["version"],
                persist=True,
            )
            self.__light_devices.append(light)

            self.__lights.append(device["name"])

            status = light.status()
            self.__initial_light_states[device["id"]] = status["dps"]

            if light_value_max is None:
                light_value_max = light.dpset["value_max"]
            elif light_value_max != light.dpset["value_max"]:
                self.__same_value_max = False

            light.set_mode("music", nowait=False)

        if self.__same_value_max is None:
            self.__same_value_max = True

        self.__connection_status = True

        logger.info(f"Lights: {self.__lights}")

    def __send_light_state(self, brightness: int, rgb_color: List[int]) -> None:
        # Hex Format: 011112222333344445555 - transition, r, g, b, colortemp, br
        hex = ""
        hex += "%x" % 0
        hex += BulbDevice.rgb_to_hexvalue(
            rgb_color[0],
            rgb_color[1],
            rgb_color[2],
            "hsv16",
        )
        hex += "%04x" % 0
        hex += "%04x" % int(1000 * (brightness / 255))

        for light in self.__light_devices:
            light.set_value("27", hex, nowait=True)

    def __push_states(self) -> None:
        while True:
            try:
                br, cl = self.__process_queue.get(timeout=1)
                logger.debug(f"Br: {br}, R: {cl[0]}, G: {cl[1]}, B: {cl[2]}")

                self.__send_light_state(br, cl)
            except queue.Empty:
                if self.__connection_status:
                    logger.debug("Queue Empty")
                else:
                    break

    def __recover_light_state(self) -> None:
        for i in range(len(self.__light_devices)):
            light = self.__light_devices[i]

            if i == len(self.__light_devices) - 1:
                nowait = False
            else:
                nowait = True

            data = self.__initial_light_states[light.id]
            light.set_multiple_values(data, nowait=nowait)

        logger.debug("Initial State Restored")

    def __close_connection(self) -> None:
        for light in self.__light_devices:
            light.close()

        self.__connection_status = False

        logger.debug("Local Tuya Connection Closed")

    def __send_ready_signal(self) -> None:
        self.__process_connection.send("ready")

    def __process_connection_listener(self) -> None:
        while True:
            message = self.__process_connection.recv()

            if message == "kill":
                break

        self.kill()
        self.close()

    def run(self) -> None:
        try:
            self.__initialize()
            self.__connect()

            threading.Thread(
                target=self.__process_connection_listener,
            ).start()

            self.__send_ready_signal()
            self.__push_states()
        except KeyboardInterrupt:
            pass

    def kill(self) -> None:
        sleep(0.3)
        self.__recover_light_state()

        sleep(0.3)
        self.__close_connection()

        logger.debug("Local Tuya Process Finished")
