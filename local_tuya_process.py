import multiprocessing
import os
import queue
import threading
from json import dumps, loads
from multiprocessing.connection import Connection
from typing import List

import tinytuya
from tinytuya import wizard


class LocalTuyaProcess(multiprocessing.Process):
    def __init__(
        self, process_connection: Connection, process_queue: multiprocessing.Queue
    ) -> None:
        super().__init__()

        self.__process_connection = process_connection
        self.__process_queue = process_queue

        self.__connection_status = False

    def __initialize(self) -> None:
        scan = tinytuya.deviceScan(byID=True)
        print(scan)

        if not scan:
            return

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
            skip_poll=True,
        )

        os.unlink("tuya-raw.json")

        with open("devices.json", "r") as f:
            devices = loads(f.read())

            self.__devices = []
            for device in devices:
                try:
                    if device["category"] == "dj":
                        d = {
                            "id": device["id"],
                            "name": device["name"],
                            "ip_address": scan[device["id"]]["ip"],
                            "local_key": device["key"],
                            "version": scan[device["id"]]["version"],
                        }

                        self.__devices.append(d)
                except KeyError:
                    print(device)

    def __connect(self) -> None:
        self.__lights: List[tinytuya.BulbDevice] = []
        self.__initial_light_states = {}

        for device in self.__devices:
            light = tinytuya.BulbDevice(
                dev_id=device["id"],
                address=device["ip_address"],
                local_key=device["local_key"],
                version=device["version"],
                persist=True,
            )
            self.__lights.append(light)

            self.__initial_light_states[device["id"]] = light.status()["dps"]

        print(self.__initial_light_states)

        self.__connection_status = True

    def __send_light_state(self, brightness: int, rgb_color: List[int]) -> None:
        for light in self.__lights:
            light.set_brightness(int((brightness / 255) * 1000), nowait=True)
            # light.set_brightness(brightness, nowait=True)
            light.set_colour(*rgb_color, nowait=True)

    def __recover_light_state(self) -> None:
        for light in self.__lights:
            status = self.__initial_light_states[light.id]

            for key, value in status.items():
                light.set_value(index=key, value=value, nowait=False)

        print("Initial State Restored")

    def __push_states(self) -> None:
        while True:
            try:
                br, cl = self.__process_queue.get(timeout=5)
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
        self.__close_connection()

        print("Tuya Local Process Killed")
