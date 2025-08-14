import numpy as np
import sounddevice as sd


class InputStreamAudioManager:
    def __init__(self):
        self.count = 0
        self.data = np.array([[]])

    def initialize_device(self):
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

        device_details = sd.query_devices(self.input_device)
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
        ms=100,
        latency=None,
    ):
        blocksize = int(self.samplerate * ms / 1000)
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            blocksize=blocksize,
            device=self.input_device,
            channels=self.channels,
            dtype="float32",
            latency=latency,
            callback=self.callback,
            finished_callback=self.finished_callback,
            clip_off=None,
            dither_off=None,
            never_drop_input=None,
            prime_output_buffers_using_stream_callback=None,
        )

        self.freqs = np.fft.rfftfreq(blocksize, 1.0 / self.samplerate)
        self.bands = {
            "low": self.find_lower_and_upper_freqs(20, 250),
            "mid": self.find_lower_and_upper_freqs(250, 4000),
            "high": self.find_lower_and_upper_freqs(4000, 12000),
        }

        print()
        print(f"Block Size: {blocksize}")
        print(f"Freqs Shape: {self.freqs.shape}")
        print(f"Freqs Interval: {self.freqs[1]}")
        print(f"Freqs Max: {self.freqs[-1]}")
        print(f"Bands Freqs: {self.bands}")
        print()

    def find_lower_and_upper_freqs(self, ll, hl):
        li = list(map(lambda x: x > ll, self.freqs)).index(True) - 1
        ri = list(map(lambda x: x < hl, self.freqs)).index(False) + 1

        return li, ri

    def callback(self, indata, frames, time, status):
        window = np.hanning(frames)[:, None]
        magnitude = np.abs(np.fft.rfft(indata * window, axis=0))

        low_bands = magnitude[self.bands["low"][0] : self.bands["low"][1]]
        mid_bands = magnitude[self.bands["mid"][0] : self.bands["mid"][1]]
        high_bands = magnitude[self.bands["high"][0] : self.bands["high"][1]]

        low_band_avg = np.average(low_bands)
        low_band_max = np.max(low_bands)
        r = np.uint8(
            (low_band_max if low_band_max / 2 > low_band_avg else low_band_avg) * 255
        )

        mid_band_avg = np.average(mid_bands)
        mid_band_max = np.max(mid_bands)
        g = np.uint8(
            (mid_band_max if mid_band_max / 2 > mid_band_avg else mid_band_avg) * 255
        )

        high_band_avg = np.average(high_bands)
        high_band_max = np.max(high_bands)
        b = np.uint8(
            (high_band_max if high_band_max / 2 > high_band_avg else high_band_avg)
            * 255
        )

        brightness = int((max(r, g, b) / 255) * 100)

        print(f"R: {r}, G: {g}, B: {b}, Br: {brightness}")

        self.count += 1

    def finished_callback(self):
        print(self.count)
        print("Stream Completed")
