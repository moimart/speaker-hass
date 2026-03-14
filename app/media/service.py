"""Sendspin-audio media player service for Music Assistant integration."""

import asyncio
import logging
import os
import re

from app.config import Config
from app.events import EventBus

logger = logging.getLogger(__name__)


def _extract_card_name(alsa_device: str) -> str:
    """Extract card name from ALSA device string, e.g. 'plughw:CARD=S330,DEV=0' -> 'S330'."""
    match = re.search(r"CARD=([^,]+)", alsa_device)
    return match.group(1) if match else ""


def find_portaudio_device(card_name: str) -> int:
    """Find the PortAudio output device index matching the given ALSA card name.

    Returns -1 (system default) if sounddevice is unavailable or no match found.
    """
    if not card_name:
        return -1
    try:
        import sounddevice as sd  # type: ignore

        for i, dev in enumerate(sd.query_devices()):
            if card_name.lower() in dev["name"].lower() and dev["max_output_channels"] > 0:
                logger.info("Found PortAudio device %d: %s", i, dev["name"])
                return i
    except Exception:
        pass
    logger.warning("Could not find PortAudio device for card '%s', using default", card_name)
    return -1


class MediaPlayerService:
    """Runs sendspin-audio daemon for Music Assistant media playback."""

    def __init__(self, config: Config, event_bus: EventBus) -> None:
        self.config = config
        self.event_bus = event_bus
        self._ma_host: str = os.environ.get("MUSIC_ASSISTANT_HOST", "")
        self._ma_port: int = int(os.environ.get("MUSIC_ASSISTANT_PORT", "8927"))
        self._name: str = os.environ.get("SENDSPIN_NAME", config.satellite_name)
        self._device_idx: int = int(os.environ.get("SENDSPIN_AUDIO_DEVICE", "-2"))
        self._process: asyncio.subprocess.Process | None = None
        self._was_playing = False

    async def run(self) -> None:
        """Start sendspin daemon and keep it running."""
        self.event_bus.subscribe("state.changed", self._on_state_changed)

        # Auto-detect PortAudio device if not explicitly set
        device_idx = self._device_idx
        if device_idx == -2:
            card_name = _extract_card_name(self.config.snd_device)
            device_idx = find_portaudio_device(card_name)

        cmd = ["sendspin", "daemon", "--name", self._name, "--audio-device", str(device_idx)]

        if self._ma_host:
            url = f"ws://{self._ma_host}:{self._ma_port}/sendspin"
            cmd += ["--url", url]
            logger.info("Starting sendspin daemon (device=%d, MA=%s)", device_idx, url)
        else:
            logger.info("Starting sendspin daemon (device=%d, mDNS discovery)", device_idx)

        while True:
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                logger.info("Sendspin started (pid=%d)", self._process.pid)

                stderr = await self._process.stderr.read()
                returncode = await self._process.wait()

                if stderr:
                    logger.warning("Sendspin stderr: %s", stderr.decode().strip())
                logger.warning("Sendspin exited with code %d, restarting in 5s", returncode)
            except FileNotFoundError:
                logger.error("'sendspin' binary not found — is it installed?")
            except Exception:
                logger.exception("Failed to start sendspin")

            await asyncio.sleep(5)

    async def _stop_process(self) -> None:
        """Terminate the sendspin daemon to release the audio device."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._process.kill()

    async def _on_state_changed(self, _event: str, data: dict) -> None:
        """Stop sendspin during TTS/announcements so aplay can use the ALSA device."""
        state = data.get("state", "")

        if state in ("responding", "wake"):
            if self._process and self._process.returncode is None:
                self._was_playing = True
                logger.info("Stopping sendspin for voice assistant")
                await self._stop_process()

        elif state == "idle" and self._was_playing:
            # Sendspin's run() loop will restart it automatically
            logger.info("Sendspin will resume on next restart")
            self._was_playing = False
