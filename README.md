# Vibe Lights

Vibe Lights is a Python-based application that synchronizes your lights with the music you are playing on your computer. It captures audio from an input device, analyzes the audio to detect beats and determine the mood of the music, and then controls your smart lights accordingly.

## Features

- Real-time light synchronization with music.
- Beat detection to create dynamic lighting effects.
- Support for multiple backends:
  - Home Assistant (REST API)
  - Home Assistant (WebSocket)
  - Local Tuya
- Easy to configure and use.

## How it Works

The application consists of two main components: an audio processor and a backend controller.

The audio processor captures audio from a selected input device. It then performs a Fast Fourier Transform (FFT) on the audio data to analyze the frequency spectrum. Based on the energy in different frequency bands (low, mid, and high), it calculates RGB values that represent the mood of the music. It also detects beats in the audio, which are used to create dynamic lighting effects.

The backend controller receives the RGB values and beat information from the audio processor. It then sends commands to your smart lights to update their color and brightness. The application supports three different backends. For the lowest latency, it is recommended to use the Local Tuya backend, followed by the Home Assistant WebSocket backend, and then the Home Assistant REST API backend.

- **Home Assistant (REST API)**: Communicates with a Home Assistant instance through its REST API.
- **Home Assistant (WebSocket)**: Communicates with a Home Assistant instance using WebSockets for more efficient, real-time updates.
- **Local Tuya**: Communicates with Tuya devices directly on your local network.

## Supported Backends

### Home Assistant

To use the Home Assistant backend, you will need to have a Home Assistant instance set up and have the REST API or WebSocket API enabled. You will also need to generate a long-lived access token.

### Local Tuya

To use the Local Tuya backend, you will need to have Tuya-compatible smart lights. You will also need to obtain the local keys for your devices. The application includes a wizard to help you with this process.

## Installation

1.  Clone the repository:

    ```bash
    git clone https://github.com/IniyanKanmani/vibe-lights.git
    ```

2.  Install the dependencies using `uv`:

    ```bash
    uv pip install -r requirements.txt
    ```

3.  Rename the `.env.example` file to `.env` and add the following environment variables:

    ```bash
    mv .env.example .env
    ```

## Configuration

The application is configured using environment variables. The following variables are available:

- `LOG_LEVEL`: The logging level. Defaults to `INFO`.
- `BACKEND`: The backend to use. Can be `restapi`, `websocket`, or `localtuya`.
- `HOMEASSISTANT_SERVER_IP`: The IP address of your Home Assistant server.
- `HOMEASSISTANT_SERVER_PORT`: The port of your Home Assistant server.
- `HOMEASSISTANT_API_KEY`: Your Home Assistant long-lived access token.
- `TUYA_API_KEY`: Your Tuya API key.
- `TUYA_API_SECRET`: Your Tuya API secret.
- `TUYA_API_REGION`: Your Tuya API region.

## Usage

To run the application, simply run the `main.py` file using `uv`:

```bash
uv run python src/main.py
```

The application will prompt you to select an audio input device. Once you have selected a device, the application will start synchronizing your lights with the music.

## Road Map

- [x] Home Assistant REST API Support
- [x] Home Assistant WebSocket Support
- [x] Local Tuya Support
- [x] Beat Detection
- [ ] Dockerize the project
- [ ] Upload to HACS as a Home Assistant Integration

## Contributing

Contributions are welcome! If you would like to contribute to the project, please follow these steps:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix.
3.  Make your changes and commit them with a clear and descriptive message.
4.  Push your changes to your fork.
5.  Create a pull request to the main repository.

## Issues

If you encounter any issues or have suggestions for improvements, please open an issue on the [GitHub repository](https://github.com/IniyanKanmani/vibe-lights/issues).
