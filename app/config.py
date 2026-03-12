"""Configuration from environment variables."""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Wyoming satellite server port (HA connects to us)
    satellite_port: int = field(default_factory=lambda: int(os.environ.get("SATELLITE_PORT", "10700")))
    satellite_name: str = field(default_factory=lambda: os.environ.get("SATELLITE_NAME", "Speaker HASS"))

    # ALSA audio devices
    mic_device: str = field(default_factory=lambda: os.environ.get("MIC_DEVICE", "plughw:CARD=Jabra,DEV=0"))
    snd_device: str = field(default_factory=lambda: os.environ.get("SND_DEVICE", "plughw:CARD=Jabra,DEV=0"))

    # Audio format (16kHz, 16-bit, mono — Wyoming standard)
    audio_rate: int = 16000
    audio_width: int = 2  # bytes per sample
    audio_channels: int = 1
    audio_chunk_ms: int = 30  # milliseconds per chunk

    # Wake word
    wake_word_model: str = field(
        default_factory=lambda: os.environ.get("WAKE_WORD_MODEL", "/models/okay_nabu.tflite")
    )
    wake_word_name: str = field(default_factory=lambda: os.environ.get("WAKE_WORD_NAME", "okay_nabu"))
    wake_word_threshold: float = field(
        default_factory=lambda: float(os.environ.get("WAKE_WORD_THRESHOLD", "0.5"))
    )
    wake_word_cooldown: float = 2.0  # seconds after detection before re-arming

    # Web UI
    web_port: int = field(default_factory=lambda: int(os.environ.get("WEB_PORT", "8080")))

    # Sound effects
    sound_enabled: bool = field(
        default_factory=lambda: os.environ.get("SOUND_ENABLED", "true").lower() == "true"
    )

    @property
    def chunk_samples(self) -> int:
        return int(self.audio_rate * self.audio_chunk_ms / 1000)

    @property
    def chunk_bytes(self) -> int:
        return self.chunk_samples * self.audio_width * self.audio_channels
