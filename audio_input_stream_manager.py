import json
from collections import deque
from typing import Callable, Tuple

import numpy as np
import sounddevice as sd


class AudioInputStreamManager:
    def initialize_stream(self) -> None:
        device_list = sd.query_devices()
        print(device_list, end="\n\n")

        input_device = input("Choose audio stream input device: ")

        try:
            input_device = int(input_device)
            self.__input_device = input_device
        except ValueError:
            raise Exception("Invalid Input Device")

        print()

        device_details = dict(sd.query_devices(self.__input_device))
        print("Input Device: ")
        print(json.dumps(device_details, indent=4))

        print()

        self.__samplerate = int(device_details["default_samplerate"])
        max_channel_in = int(device_details["max_input_channels"])

        if max_channel_in == 0:
            raise Exception("Device doesn't currently have input channels available")

        channel_in = input(
            f"Number of channels to stream in with (Max {max_channel_in}): "
        )

        try:
            channel_in = int(channel_in)

            if channel_in == 0:
                raise Exception("Number of channel cannot be zero")
            elif channel_in > max_channel_in:
                raise Exception(
                    f"Number of channels cannot be more than {max_channel_in}"
                )

            self.__channels = channel_in
        except ValueError:
            raise Exception("Invalid number of channels")

    def build_stream(
        self,
        ms: float = 100,
        latency: float | None = None,
        callback: Callable | None = None,
        finished_callback: Callable | None = None,
    ) -> None:
        self.__input_stream = sd.InputStream(
            samplerate=self.__samplerate,
            blocksize=int((ms * self.__samplerate) / 1000),
            device=self.__input_device,
            channels=self.__channels,
            dtype="float32",
            latency=latency,
            callback=self.__process_audio,
            finished_callback=self.__finish_processing,
            clip_off=None,
            dither_off=None,
            never_drop_input=None,
            prime_output_buffers_using_stream_callback=None,
        )

        blocksize = self.__input_stream.blocksize

        self.__freqs = np.fft.rfftfreq(blocksize, 1.0 / self.__samplerate)
        self.__bands = {
            "low": self.__find_lower_and_upper_freqs(20, 250),
            "mid": self.__find_lower_and_upper_freqs(250, 2000),
            "high": self.__find_lower_and_upper_freqs(2000, 16000),
        }

        self.__callback = callback
        self.__finished_callback = finished_callback

        self.__max_possible_amp = (blocksize // 2) * 1.0 * 0.5

        self.__beat_cooldown = 0
        self.__prev_magnitude = None
        self.__mag_history = deque(maxlen=10)

        print()
        print(f"Block Size: {blocksize}")
        print(f"Freqs Shape: {self.__freqs.shape}")
        print(f"Freqs Interval: {self.__freqs[1]}")
        print(f"Freqs Max: {self.__freqs[-1]}")
        print(f"Bands Freqs: {self.__bands}")
        print(f"Max Possible Amp: {self.__max_possible_amp}")
        print()

    def start_stream(self) -> None:
        self.__input_stream.start()

    def __find_lower_and_upper_freqs(self, ll: int, hl: int) -> Tuple[int, int]:
        li = list(map(lambda x: x > ll, self.__freqs)).index(True) - 1
        ri = list(map(lambda x: x < hl, self.__freqs)).index(False) + 1

        return li, ri

    def __process_audio(self, indata: np.ndarray, frames: int, *_) -> None:
        window = np.hanning(frames)[:, None]
        magnitude = np.abs(np.fft.rfft(indata * window, axis=0))

        beat_detected = False

        if self.__prev_magnitude is None:
            self.__prev_magnitude = np.copy(magnitude)
            return

        mag_diff = magnitude - self.__prev_magnitude
        mag_diff = np.maximum(0, mag_diff)

        flux = np.sum(mag_diff)

        if len(self.__mag_history) > 0:
            if self.__beat_cooldown > 0:
                self.__beat_cooldown -= 1
            else:
                mag_history_avg = np.average(self.__mag_history)
                threashold = mag_history_avg * 1.5

                if flux > threashold:
                    beat_detected = True
                    print("Beat Detected")
                    self.__beat_cooldown = 7

        self.__mag_history.append(flux)
        self.__prev_magnitude = np.copy(magnitude)

        low_bands = magnitude[self.__bands["low"][0] : self.__bands["low"][1]]
        mid_bands = magnitude[self.__bands["mid"][0] : self.__bands["mid"][1]]
        high_bands = magnitude[self.__bands["high"][0] : self.__bands["high"][1]]

        # Calculate Red
        # low_log = np.log(low_bands + 1)
        # low_min_log = np.min(low_log)
        # low_max_log = np.max(low_log)

        low_min_log = 0.5
        low_max_log = 10.0

        r = np.sqrt(np.average(np.power(low_bands, 2)))
        r = np.log(r + 1)
        r = ((r - low_min_log) / (low_max_log - low_min_log)) * 255
        r = np.clip(r, 0, 255)

        # Calculate Green
        # mid_log = np.log(mid_bands + 1)
        # mid_min_log = np.min(mid_log)
        # mid_max_log = np.max(mid_log)

        mid_min_log = 0.25
        mid_max_log = 5.0

        g = np.sqrt(np.average(np.power(mid_bands, 2)))
        g = np.log(g + 1)
        g = ((g - mid_min_log) / (mid_max_log - mid_min_log)) * 255
        g = np.clip(g, 0, 255)

        # Calculate Blue
        # high_log = np.log(high_bands + 1)
        # high_min_log = np.min(high_log)
        # high_max_log = np.max(high_log)

        high_min_log = 0.1
        high_max_log = 2.5

        b = np.sqrt(np.average(np.power(high_bands, 2)))
        b = np.log(b + 1)
        b = ((b - high_min_log) / (high_max_log - high_min_log)) * 255
        b = np.clip(b, 0, 255)

        # Calculate Brightness
        if beat_detected:
            br = 255
        else:
            br_mag = magnitude[self.__bands["low"][0] : self.__bands["high"][1]]
            mag_log = np.log(br_mag + 1)
            mag_min_log = np.min(mag_log)
            mag_max_log = np.max(mag_log)

            br = np.sqrt(np.average(np.power(br_mag, 2)))
            br = np.log(br + 1)
            br = ((br - mag_min_log) / (mag_max_log - mag_min_log)) * 255
            br = np.clip(br, 0, 255)

        # print(br, r, g, b)

        if self.__callback:
            self.__callback(int(br), [int(r), int(g), int(b)])

        # if len(self.__data) < self.__samples_to_average - 1:
        #     self.__data.append([br, r, g, b])
        # else:
        #     br, r, g, b = np.array(np.average(self.__data, axis=0), dtype=np.uint8)
        #
        #     if self.__callback:
        #         self.__callback(int(br), [int(r), int(g), int(b)])
        #
        #     self.__data.clear()

    def __finish_processing(self) -> None:
        if self.__finished_callback:
            self.__finished_callback()

        print("Input Stream Finished")

    def is_stream_alive(self) -> bool:
        return self.__input_stream.active

    def close_stream(self) -> None:
        self.__input_stream.close()

        print("Input Stream Closed")
