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
        print("Input Device: ", device_details)

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
            blocksize=1024,
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
            "mid": self.__find_lower_and_upper_freqs(250, 4000),
            "high": self.__find_lower_and_upper_freqs(4000, 12000),
        }

        self.__callback = callback
        self.__finished_callback = finished_callback

        self.__data = []
        self.__samples_to_average = int((ms * self.__samplerate) / (blocksize * 1000))

        self.__max_possible_amp = (blocksize // 2) * 1.0 * 0.5

        print()
        print(f"Block Size: {blocksize}")
        print(f"Freqs Shape: {self.__freqs.shape}")
        print(f"Freqs Interval: {self.__freqs[1]}")
        print(f"Freqs Max: {self.__freqs[-1]}")
        print(f"Bands Freqs: {self.__bands}")
        print(f"Samples Number: {self.__samples_to_average}")
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

        # print(np.min(magnitude), np.average(magnitude), np.max(magnitude))

        br = (np.max(magnitude) / self.__max_possible_amp) * 255
        br = np.clip(br, 0, 255)

        low_bands = magnitude[self.__bands["low"][0] : self.__bands["low"][1]]
        mid_bands = magnitude[self.__bands["mid"][0] : self.__bands["mid"][1]]
        high_bands = magnitude[self.__bands["high"][0] : self.__bands["high"][1]]

        r = (np.max(low_bands) / self.__max_possible_amp) * 255
        r = np.clip(r, 0, 255)

        # low_band_avg = np.average(low_bands)
        # low_band_max = np.max(low_bands)
        # r = int(
        #     (low_band_max if low_band_max / 2 > low_band_avg else low_band_avg) * 255
        # )

        g = (np.max(mid_bands) / self.__max_possible_amp) * 255
        g = np.clip(r, 0, 255)

        # mid_band_avg = np.average(mid_bands)
        # mid_band_max = np.max(mid_bands)
        # g = int(
        #     (mid_band_max if mid_band_max / 2 > mid_band_avg else mid_band_avg) * 255
        # )

        b = (np.max(high_bands) / self.__max_possible_amp) * 255
        b = np.clip(r, 0, 255)

        # print(br, r, g, b)

        # high_band_avg = np.average(high_bands)
        # high_band_max = np.max(high_bands)
        # b = int(
        #     (high_band_max if high_band_max / 2 > high_band_avg else high_band_avg)
        #     * 255
        # )

        if len(self.__data) < self.__samples_to_average - 1:
            self.__data.append([br, r, g, b])
        else:
            br, r, g, b = np.array(np.average(self.__data, axis=0), dtype=np.uint8)

            if self.__callback:
                self.__callback(int(br), [int(r), int(g), int(b)])

            self.__data.clear()

    def __finish_processing(self) -> None:
        if self.__finished_callback:
            self.__finished_callback()

        print("Input Stream Finished")

    def is_stream_alive(self) -> bool:
        return self.__input_stream.active

    def close_stream(self) -> None:
        self.__input_stream.close()

        print("Input Stream Closed")
