import asyncio
import queue
import threading

from home_assistant_websocket import HomeAssistantWebSocket


class WebsocketQueueLoop:
    def __init__(
        self, light_data_queue: queue.Queue, ha_websocket: HomeAssistantWebSocket
    ):
        self.light_data_queue = light_data_queue
        self.ha_websocket = ha_websocket

    def initialize_loop(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.__loop_runner, daemon=True).start()

    def __loop_runner(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def push_states(self):
        while True:
            br, cl = self.light_data_queue.get()

            self.loop.call_soon_threadsafe(
                asyncio.create_task, self.ha_websocket.send_light_state(br, cl)
            )

            print(f"Br: {br}, R: {cl[0]}, G: {cl[1]}, B: {cl[2]}")
