"""Main entry point — starts all voice assistant services."""

import asyncio
import logging
import sys

import uvicorn

from app.audio.player import AudioPlayer
from app.audio.recorder import AudioRecorder
from app.config import Config
from app.events import EventBus
from app.satellite.service import SatelliteService
from app.wakeword.detector import WakeWordDetector
from app.media.service import MediaPlayerService
from app.web.server import WebServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("speaker-hass")


async def main() -> None:
    config = Config()
    event_bus = EventBus()

    logger.info("Speaker HASS starting")
    logger.info("  Satellite: %s (port %d)", config.satellite_name, config.satellite_port)
    logger.info("  Mic: %s | Speaker: %s", config.mic_device, config.snd_device)
    logger.info("  Wake word: %s (threshold %.2f)", config.wake_word_name, config.wake_word_threshold)
    logger.info("  Web UI: http://0.0.0.0:%d", config.web_port)
    logger.info("  MPD: port 6600 (media_player)")

    recorder = AudioRecorder(config, event_bus)
    player = AudioPlayer(config)
    detector = WakeWordDetector(config, event_bus)
    satellite = SatelliteService(config, event_bus, player)
    media_player = MediaPlayerService(config, event_bus)
    web_server = WebServer(config, event_bus)

    app = web_server.create_app()
    uvi_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=config.web_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(uvi_config)

    await asyncio.gather(
        recorder.run(),
        detector.run(),
        satellite.run(),
        media_player.run(),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
