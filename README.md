# Speaker HASS

A Docker-based voice assistant for Raspberry Pi that turns a USB Jabra speaker/microphone into a full Home Assistant voice satellite — like the Voice Preview Edition, but built from off-the-shelf hardware.

Local wake word detection via **microWakeWord**, real-time voice pipeline status through a clean **web UI**, and seamless integration with Home Assistant through the **Wyoming protocol**.

---

## Features

- **Wake word detection** — runs locally on the Pi using microWakeWord (no cloud dependency)
- **Wyoming satellite** — connects to Home Assistant's voice pipeline (STT → intent → TTS)
- **Web UI** — real-time status at `http://<pi-ip>:8080` with animated state orb, transcript history, and settings
- **USB audio** — works with Jabra Speak and similar USB speakerphones via ALSA
- **Docker** — single container, one command to deploy
- **Dark mode** — automatic, follows system preference

## How It Works

```
┌─────────────────────────────────────────────────────┐
│  Raspberry Pi                                       │
│                                                     │
│  ┌───────────┐    ┌──────────────┐    ┌──────────┐  │
│  │  Jabra    │───▶│ microWakeWord│───▶│ Wyoming  │──────▶ Home Assistant
│  │  USB Mic  │    │  Detection   │    │ Satellite│◀──────  (STT/Intent/TTS)
│  └───────────┘    └──────────────┘    └──────────┘  │
│                                            │        │
│  ┌───────────┐                      ┌──────┴─────┐  │
│  │  Jabra    │◀─────────────────────│  Web UI    │  │
│  │  Speaker  │   TTS playback       │  :8080     │  │
│  └───────────┘                      └────────────┘  │
└─────────────────────────────────────────────────────┘
```

**State machine:** Idle → Wake Detected → Listening → Processing → Responding → Idle

## Prerequisites

- Raspberry Pi 4/5 (or any ARM64/x86 Linux host)
- USB speakerphone (Jabra Speak 410/510/710 recommended)
- Home Assistant with a configured voice pipeline (Whisper + Piper or cloud STT/TTS)
- Docker and Docker Compose

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url> speaker-hass
cd speaker-hass
```

### 2. Choose a wake word

Four wake words are built-in (no model download needed):

- `okay_nabu` (default)
- `hey_jarvis`
- `hey_mycroft`
- `alexa`

Set your choice via the `WAKE_WORD_NAME` environment variable in `docker-compose.yml`.

### 3. Find your audio device

On the Pi, with the Jabra plugged in:

```bash
arecord -l   # Find the card name for the microphone
aplay -l     # Find the card name for the speaker
```

Look for your Jabra device. The card name is typically `Jabra` — the default config uses `plughw:CARD=Jabra,DEV=0`.

### 4. Edit environment variables

In `docker-compose.yml`, update:

```yaml
environment:
  - HA_HOST=192.168.1.100        # Your Home Assistant IP
  - MIC_DEVICE=plughw:CARD=Jabra,DEV=0
  - SND_DEVICE=plughw:CARD=Jabra,DEV=0
  - WAKE_WORD_NAME=okay_nabu     # or hey_jarvis, alexa, hey_mycroft
```

### 5. Launch

```bash
docker compose up -d
```

### 6. Add to Home Assistant

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Wyoming**
3. Enter the Pi's IP address and port `10700`
4. The satellite appears as a voice assistant device

### 7. Open the Web UI

Navigate to `http://<pi-ip>:8080` in your browser.

## Web UI

The web interface shows the voice assistant's state in real-time:

| State | Orb Color | Meaning |
|-------|-----------|---------|
| Idle | Blue | Listening for wake word |
| Wake Detected | Green | Wake word heard |
| Listening | Green (pulsing) | Streaming audio to HA |
| Processing | Amber (pulsing) | HA is processing intent |
| Responding | Purple (pulsing) | Playing TTS response |
| Error | Red | Connection lost |

The settings page at `/settings` shows connection details and has a **Trigger Pipeline** button for testing without a wake word.

## Configuration

All configuration is via environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `HA_HOST` | `homeassistant.local` | Home Assistant hostname or IP |
| `HA_PORT` | `10300` | HA Wyoming integration port |
| `SATELLITE_PORT` | `10700` | Port this satellite listens on |
| `SATELLITE_NAME` | `Speaker HASS` | Name shown in HA |
| `MIC_DEVICE` | `plughw:CARD=Jabra,DEV=0` | ALSA capture device |
| `SND_DEVICE` | `plughw:CARD=Jabra,DEV=0` | ALSA playback device |
| `WAKE_WORD_NAME` | `okay_nabu` | Built-in: `okay_nabu`, `hey_jarvis`, `hey_mycroft`, `alexa` |
| `WAKE_WORD_MODEL` | — | Path to custom model config (optional, overrides built-in) |
| `WEB_PORT` | `8080` | Web UI port |
| `SOUND_ENABLED` | `true` | Enable sound effects |

## Project Structure

```
speaker-hass/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── app/
│   ├── main.py              # Entry point
│   ├── config.py            # Environment-based configuration
│   ├── events.py            # Async pub/sub event bus
│   ├── audio/
│   │   ├── recorder.py      # ALSA mic capture (arecord)
│   │   └── player.py        # ALSA playback (aplay)
│   ├── wakeword/
│   │   └── detector.py      # microWakeWord integration
│   ├── satellite/
│   │   ├── state.py         # State machine
│   │   └── service.py       # Wyoming protocol handler
│   └── web/
│       ├── server.py        # FastAPI + WebSocket server
│       └── static/          # Web UI (HTML/CSS/JS)
├── models/                  # Wake word .tflite models
└── config/                  # Runtime configuration
```

## Troubleshooting

**No audio devices found**
```bash
# Check the Jabra is detected
lsusb | grep Jabra
# List ALSA devices
arecord -l
```

**Wake word not triggering**
- Lower `WAKE_WORD_THRESHOLD` (e.g., `0.3`)
- Ensure the model file exists in `models/`
- Check logs: `docker compose logs -f`

**Home Assistant not connecting**
- Verify HA can reach the Pi on port `10700`
- Check that Wyoming integration is added in HA
- The satellite runs a TCP server — HA connects to it, not the other way around

**Permission denied on audio device**
```bash
# Add your user to the audio group on the host
sudo usermod -aG audio $USER
```

## License

MIT
