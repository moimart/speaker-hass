"""Audio capture from ALSA microphone via arecord subprocess."""

import asyncio
import logging

from app.config import Config
from app.events import EventBus

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Captures PCM audio from an ALSA device and publishes chunks to the event bus."""

    def __init__(self, config: Config, event_bus: EventBus) -> None:
        self.config = config
        self.event_bus = event_bus
        self._process: asyncio.subprocess.Process | None = None
        self._running = False

    async def run(self) -> None:
        """Start recording and publish audio chunks continuously."""
        self._running = True
        while self._running:
            try:
                await self._record_loop()
            except Exception:
                logger.exception("Audio recorder crashed, restarting in 2s")
                await asyncio.sleep(2)

    async def _record_loop(self) -> None:
        cmd = [
            "arecord",
            "-D", self.config.mic_device,
            "-r", str(self.config.audio_rate),
            "-c", str(self.config.audio_channels),
            "-f", "S16_LE",
            "-t", "raw",
            "--buffer-size", str(self.config.chunk_samples * 4),
        ]
        logger.info("Starting audio capture: %s", " ".join(cmd))

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        assert self._process.stdout is not None
        chunk_size = self.config.chunk_bytes

        try:
            while self._running:
                data = await self._process.stdout.readexactly(chunk_size)
                await self.event_bus.publish("audio.chunk", data)
        except asyncio.IncompleteReadError:
            logger.warning("Audio stream ended unexpectedly")
        finally:
            if self._process.returncode is None:
                self._process.terminate()
                await self._process.wait()

    async def stop(self) -> None:
        self._running = False
        if self._process and self._process.returncode is None:
            self._process.terminate()
