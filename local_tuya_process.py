import multiprocessing
import os
import queue
import threading
from json import dumps, loads
from multiprocessing.connection import Connection
from time import sleep
from typing import List

from tinytuya import BulbDevice, scanner, wizard


class LocalTuyaProcess(multiprocessing.Process):
    def __init__(
        self, process_connection: Connection, process_queue: multiprocessing.Queue
    ) -> None:
        super().__init__()

        scanner.SCANTIME = 30

        self.__process_connection = process_connection
        self.__process_queue = process_queue

        self.__connection_status = False

    def __initialize(self) -> None:
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
                if device["category"] == "dj":
                    data = {
                        "id": device["id"],
                        "name": device["name"],
                        "ip_address": device["ip"],
                        "local_key": device["key"],
                        "version": device["version"],
                    }

                    self.__devices.append(data)

        os.unlink("snapshot.json")
        os.unlink("tuya-raw.json")
        os.unlink("devices.json")
        os.unlink("tinytuya.json")

    def __connect(self) -> None:
        self.__lights = []
        self.__initial_light_states = {}

        for device in self.__devices:
            light = BulbDevice(
                dev_id=device["id"],
                address=device["ip_address"],
                local_key=device["local_key"],
                version=device["version"],
                persist=True,
            )
            self.__lights.append(light)

            status = light.status()
            self.__initial_light_states[device["id"]] = status["dps"]

            light.set_mode("colour", nowait=True)

        self.__connection_status = True

    def __send_light_state(self, brightness: int, rgb_color: List[int]) -> None:
        br = brightness / 1000
        hex = BulbDevice.rgb_to_hexvalue(*rgb_color, hexformat="hsv16")
        h, s, _ = BulbDevice.hexvalue_to_hsv(hex, "hsv16")
        value = BulbDevice.hsv_to_hexvalue(h, s, br, "hsv16")

        for i in range(len(self.__lights)):
            # br = brightness / light.dpset["value_max"]
            # value = BulbDevice.hsv_to_hexvalue(h, s, br, "hsv16")

            self.__lights[i].set_multiple_values(
                {
                    "21": "colour",
                    "24": value,
                },
                nowait=True,
            )

    def __recover_light_state(self) -> None:
        for i in range(len(self.__lights)):
            light = self.__lights[i]

            if i == len(self.__lights) - 1:
                nowait = False
            else:
                nowait = True

            data = self.__initial_light_states[light.id]
            light.set_multiple_values(data, nowait=nowait)

        print("Initial State Restored")

    def __push_states(self) -> None:
        while True:
            try:
                br, cl = self.__process_queue.get(timeout=3)
                print(f"Br: {br}, R: {cl[0]}, G: {cl[1]}, B: {cl[2]}")

                self.__send_light_state(br, cl)
            except queue.Empty:
                print("Queue Empty")
            finally:
                if not self.__connection_status:
                    print("Queue Closed")
                    break

    def __close_connection(self) -> None:
        for light in self.__lights:
            light.close()

        self.__connection_status = False

        print("Connection Closed")

    def __send_ready_signal(self) -> None:
        self.__process_connection.send("ready")

    def __process_connection_listener(self) -> None:
        while True:
            message = self.__process_connection.recv()

            if message == "kill":
                self.kill()
                self.close()

                break

    def run(self) -> None:
        self.__initialize()
        self.__connect()

        threading.Thread(target=self.__process_connection_listener, daemon=True).start()

        self.__send_ready_signal()
        self.__push_states()

    def kill(self) -> None:
        self.__recover_light_state()
        sleep(0.25)
        self.__close_connection()

        print("Tuya Local Process Killed")
