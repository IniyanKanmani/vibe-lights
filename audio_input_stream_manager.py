from typing import Callable, Tuple

import numpy as np
import sounddevice as sd

from utils import clamp


class AudioInputStreamManager:
    def initialize_input_device(self) -> None:
        device_list = sd.query_devices()
        print(device_list, end="\n\n")

        input_device = input("Choose audio stream input device: ")

        try:
            input_device = int(input_device)
            self.input_device = input_device
        except ValueError:
            print("Invalid Input Device")

            return

        print()

        device_details = dict(sd.query_devices(self.input_device))
        print("Input Device: ", device_details)

        print()

        self.samplerate = int(device_details["default_samplerate"])
        max_channel_in = int(device_details["max_input_channels"])

        if max_channel_in == 0:
            print("Device doesn't currently have input channels available")

            return

        channel_in = input(
            f"Number of channels to stream in with (Max {max_channel_in}): "
        )

        try:
            channel_in = int(channel_in)
            if channel_in == 0:
                print("Number of channel cannot be zero")

                return
            elif channel_in > max_channel_in:
                print(f"Number of channels cannot be more than {max_channel_in}")

                return

            self.channels = channel_in
        except ValueError:
            print("Invalid number of channels")

            return

    def build_stream(
        self,
        ms: float = 100,
        latency: float | None = None,
        callback: Callable | None = None,
        finished_callback: Callable | None = None,
    ) -> None:
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            blocksize=1024,
            device=self.input_device,
            channels=self.channels,
            dtype="float32",
            latency=latency,
            callback=self.listen,
            finished_callback=self.finish,
            clip_off=None,
            dither_off=None,
            never_drop_input=None,
            prime_output_buffers_using_stream_callback=None,
        )

        blocksize = self.stream.blocksize
        print(f"Block Size: {blocksize}")

        self.freqs = np.fft.rfftfreq(blocksize, 1.0 / self.samplerate)
        self.bands = {
            "low": self.__find_lower_and_upper_freqs(20, 250),
            "mid": self.__find_lower_and_upper_freqs(250, 4000),
            "high": self.__find_lower_and_upper_freqs(4000, 12000),
        }

        self.callback = callback
        self.finished_callback = finished_callback

        self.data = []
        self.samples_to_average = int((ms * self.samplerate) / (blocksize * 1000))

        print()
        print(f"Block Size: {blocksize}")
        print(f"Freqs Shape: {self.freqs.shape}")
        print(f"Freqs Interval: {self.freqs[1]}")
        print(f"Freqs Max: {self.freqs[-1]}")
        print(f"Bands Freqs: {self.bands}")
        print(f"Samples Number: {self.samples_to_average}")
        print()

    def __find_lower_and_upper_freqs(self, ll: int, hl: int) -> Tuple[int, int]:
        li = list(map(lambda x: x > ll, self.freqs)).index(True) - 1
        ri = list(map(lambda x: x < hl, self.freqs)).index(False) + 1

        return li, ri

    def listen(self, indata: np.ndarray, frames: int, *_) -> None:
        window = np.hanning(frames)[:, None]
        magnitude = np.abs(np.fft.rfft(indata * window, axis=0))

        low_bands = magnitude[self.bands["low"][0] : self.bands["low"][1]]
        mid_bands = magnitude[self.bands["mid"][0] : self.bands["mid"][1]]
        high_bands = magnitude[self.bands["high"][0] : self.bands["high"][1]]

        low_band_avg = np.average(low_bands)
        low_band_max = np.max(low_bands)
        r = int(
            (low_band_max if low_band_max / 2 > low_band_avg else low_band_avg) * 255
        )

        mid_band_avg = np.average(mid_bands)
        mid_band_max = np.max(mid_bands)
        g = int(
            (mid_band_max if mid_band_max / 2 > mid_band_avg else mid_band_avg) * 255
        )

        high_band_avg = np.average(high_bands)
        high_band_max = np.max(high_bands)
        b = int(
            (high_band_max if high_band_max / 2 > high_band_avg else high_band_avg)
            * 255
        )

        br = clamp(0, max(r, g, b), 255)

        if len(self.data) < self.samples_to_average - 1:
            self.data.append([br, r, g, b])
        else:
            br, r, g, b = np.array(np.average(self.data, axis=0), dtype=np.uint8)
            if self.callback:
                self.callback(int(br), [int(r), int(g), int(b)])
            self.data.clear()

    def finish(self) -> None:
        if self.finished_callback:
            self.finished_callback()
        self.close()

    def close(self) -> None:
        self.stream.close()
