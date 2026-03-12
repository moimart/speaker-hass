"""Audio playback to ALSA speaker via aplay subprocess."""

import asyncio
import logging

from app.config import Config

logger = logging.getLogger(__name__)


class AudioPlayer:
    """Plays PCM audio through an ALSA device."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._lock = asyncio.Lock()

    async def play(self, audio_data: bytes, rate: int = 0, width: int = 0, channels: int = 0) -> None:
        """Play raw PCM audio bytes through the speaker."""
        rate = rate or self.config.audio_rate
        width = width or self.config.audio_width
        channels = channels or self.config.audio_channels

        fmt_map = {1: "U8", 2: "S16_LE", 4: "S32_LE"}
        fmt = fmt_map.get(width, "S16_LE")

        cmd = [
            "aplay",
            "-D", self.config.snd_device,
            "-r", str(rate),
            "-c", str(channels),
            "-f", fmt,
            "-t", "raw",
        ]

        async with self._lock:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.communicate(input=audio_data)

    async def play_chunks(self, chunks: list[bytes], rate: int = 0, width: int = 0, channels: int = 0) -> None:
        """Play a list of audio chunks concatenated."""
        if chunks:
            await self.play(b"".join(chunks), rate=rate, width=width, channels=channels)
