import sounddevice as sd


class BasicAudioManager:
    def define_io_devices(self):
        print(sd.query_devices())
        print()

        input_device = input("Choose the Input Device Id: ")
        output_device = input("Choose the Output Device Id: ")

        try:
            self.input_device = int(input_device)
        except ValueError:
            print("Invalid Input Device Id")
            return

        try:
            self.output_device = int(output_device)
        except ValueError:
            print("Invalid Output Device Id")
            return

        print()

        input_devices_details = sd.query_devices(self.input_device)
        print("Input Device: ", input_devices_details)

        print()

        output_devices_details = sd.query_devices(self.output_device)
        print("Output Device: ", output_devices_details)

        print()

        self.fs_in = int(input_devices_details["default_samplerate"])
        self.fs_out = int(output_devices_details["default_samplerate"])

        self.channel_in = int(input_devices_details["max_input_channels"])
        self.channel_out = int(output_devices_details["max_output_channels"])

        if self.channel_in == 0:
            print("No Input Channel Available")
            return

        if self.channel_out == 0:
            print("No Output Channel Available")
            return

        channel_in = input(f"Number of channels to record on (Max {self.channel_in}): ")
        channel_out = input(f"Number of channels to play on (Max {self.channel_out}): ")

        try:
            channel_in = int(channel_in)
            if channel_in <= self.channel_in:
                self.channel_in = channel_in
            else:
                print("Invalid number of input channels")
                return
        except ValueError:
            print("Invalid number of input channels")
            return

        try:
            channel_out = int(channel_out)
            if channel_out <= self.channel_out:
                self.channel_out = channel_out
            else:
                print("Invalid number of output channels")
                return
        except ValueError:
            print("Invalid number of output channels")
            return

        self.duration = 10

        sd.default.samplerate = self.fs_in
        sd.default.channels = self.channel_in, self.channel_out
        sd.default.device = self.input_device, self.output_device

        print(sd.query_devices())
        print()

    def record_audio(self):
        print("Recording")
        self.recording = sd.rec(
            frames=int(self.duration * self.fs_in),
            samplerate=self.fs_in,
            channels=self.channel_in,
            blocking=True,
        )
        print("Recorded")

    def play_audio(self):
        print("Playing")
        sd.play(self.recording, samplerate=self.fs_out, blocking=True)
        print("Completed")
