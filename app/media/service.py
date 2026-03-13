"""MPD-based media player service for Home Assistant integration."""

import asyncio
import logging
import os
from pathlib import Path

from app.config import Config
from app.events import EventBus

logger = logging.getLogger(__name__)

MPD_CONF_TEMPLATE = """\
music_directory     "/var/lib/mpd/music"
playlist_directory  "/var/lib/mpd/playlists"
db_file             "/var/lib/mpd/database"
log_file            "syslog"
pid_file            "/var/lib/mpd/pid"
state_file          "/var/lib/mpd/state"
sticker_file        "/var/lib/mpd/sticker.sql"

bind_to_address     "0.0.0.0"
port                "{mpd_port}"

auto_update         "yes"

audio_output {{
    type        "alsa"
    name        "Speaker"
    device      "{snd_device}"
    mixer_type  "software"
}}

# HTTP stream input support
input {{
    plugin      "curl"
}}
"""


class MediaPlayerService:
    """Manages MPD for media playback alongside voice assistant."""

    def __init__(self, config: Config, event_bus: EventBus) -> None:
        self.config = config
        self.event_bus = event_bus
        self._mpd_port = int(os.environ.get("MPD_PORT", "6600"))
        self._process: asyncio.subprocess.Process | None = None
        self._was_playing = False

    async def run(self) -> None:
        """Start MPD and keep it running."""
        self.event_bus.subscribe("state.changed", self._on_state_changed)

        # Create required directories
        for d in ["/var/lib/mpd/music", "/var/lib/mpd/playlists"]:
            os.makedirs(d, exist_ok=True)

        # Generate config
        conf_path = "/var/lib/mpd/mpd.conf"
        conf = MPD_CONF_TEMPLATE.format(
            snd_device=self.config.snd_device,
            mpd_port=self._mpd_port,
        )
        Path(conf_path).write_text(conf)

        logger.info("Starting MPD on port %d (device: %s)", self._mpd_port, self.config.snd_device)

        while True:
            try:
                self._process = await asyncio.create_subprocess_exec(
                    "mpd", "--no-daemon", conf_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                logger.info("MPD started (pid=%d)", self._process.pid)

                # Read stderr for any errors
                stderr = await self._process.stderr.read()
                returncode = await self._process.wait()

                if stderr:
                    logger.warning("MPD stderr: %s", stderr.decode().strip())
                logger.warning("MPD exited with code %d, restarting in 5s", returncode)
            except Exception:
                logger.exception("Failed to start MPD")

            await asyncio.sleep(5)

    async def _mpc(self, *args: str) -> str:
        """Run an mpc command and return stdout."""
        cmd = ["mpc", "-p", str(self._mpd_port), *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip()
        except Exception:
            return ""

    async def _is_playing(self) -> bool:
        """Check if MPD is currently playing."""
        status = await self._mpc("status")
        return "[playing]" in status

    async def _on_state_changed(self, _event: str, data: dict) -> None:
        """Pause MPD during TTS/announcements, resume after."""
        state = data.get("state", "")

        if state in ("responding", "wake"):
            # Voice assistant needs the speaker — pause MPD
            self._was_playing = await self._is_playing()
            if self._was_playing:
                logger.info("Pausing MPD for voice assistant")
                await self._mpc("pause")

        elif state == "idle" and self._was_playing:
            # Voice assistant done — resume MPD
            logger.info("Resuming MPD after voice assistant")
            await self._mpc("play")
            self._was_playing = False
