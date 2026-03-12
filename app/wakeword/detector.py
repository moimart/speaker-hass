"""Wake word detection using pymicro-wakeword."""

import asyncio
import logging
import time

from app.config import Config
from app.events import EventBus

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """Streams audio through microWakeWord and fires detection events."""

    def __init__(self, config: Config, event_bus: EventBus) -> None:
        self.config = config
        self.event_bus = event_bus
        self._wakeword = None
        self._features = None
        self._enabled = True
        self._last_detection = 0.0

    async def run(self) -> None:
        """Subscribe to audio chunks and run detection."""
        try:
            from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
            from pymicro_wakeword.const import Model as BuiltinModel

            self._features = MicroWakeWordFeatures()

            # Try built-in model first, fall back to file path
            builtin_map = {m.value: m for m in BuiltinModel}
            if self.config.wake_word_name in builtin_map:
                logger.info("Loading built-in wake word model: %s", self.config.wake_word_name)
                self._wakeword = MicroWakeWord.from_builtin(builtin_map[self.config.wake_word_name])
            else:
                logger.info("Loading wake word model from config: %s", self.config.wake_word_model)
                self._wakeword = MicroWakeWord.from_config(self.config.wake_word_model)

            logger.info("Wake word model loaded successfully")
        except Exception:
            logger.exception("Failed to load wake word model")
            return

        self.event_bus.subscribe("audio.chunk", self._on_audio_chunk)
        self.event_bus.subscribe("state.changed", self._on_state_changed)

        # Keep running
        while True:
            await asyncio.sleep(1)

    async def _on_state_changed(self, _event: str, data: dict) -> None:
        """Disable detection while pipeline is active."""
        state = data.get("state", "")
        self._enabled = state == "idle"

    async def _on_audio_chunk(self, _event: str, data: bytes) -> None:
        """Process an audio chunk for wake word detection."""
        if not self._enabled or self._wakeword is None or self._features is None:
            return

        now = time.monotonic()
        if now - self._last_detection < self.config.wake_word_cooldown:
            return

        # Extract audio features from raw PCM (16kHz 16-bit mono)
        for features in self._features.process_streaming(data):
            detected = self._wakeword.process_streaming(features)
            if detected:
                self._last_detection = now
                logger.info("Wake word detected!")
                self._wakeword.reset()
                self._features.reset()
                await self.event_bus.publish("wakeword.detected", {
                    "name": self.config.wake_word_name,
                    "timestamp": now,
                })
                return
