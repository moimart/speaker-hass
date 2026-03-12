"""Voice satellite state machine."""

from enum import Enum


class SatelliteState(str, Enum):
    IDLE = "idle"
    WAKE_DETECTED = "wake"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"
    ERROR = "error"

    @property
    def label(self) -> str:
        labels = {
            "idle": "Ready",
            "wake": "Wake Word Detected",
            "listening": "Listening",
            "processing": "Processing",
            "responding": "Speaking",
            "error": "Error",
        }
        return labels.get(self.value, self.value.title())
