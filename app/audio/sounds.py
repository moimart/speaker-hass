"""Procedural sound effects — short tones generated as PCM audio."""

import math
import struct


def _generate_tone(freq: float, duration: float, volume: float = 0.3,
                   rate: int = 16000, fade_ms: float = 10.0) -> bytes:
    """Generate a sine wave tone with fade in/out."""
    n_samples = int(rate * duration)
    fade_samples = int(rate * fade_ms / 1000)
    samples = []
    for i in range(n_samples):
        t = i / rate
        sample = math.sin(2 * math.pi * freq * t) * volume

        # Fade in
        if i < fade_samples:
            sample *= i / fade_samples
        # Fade out
        elif i > n_samples - fade_samples:
            sample *= (n_samples - i) / fade_samples

        samples.append(int(sample * 32767))

    return struct.pack(f"<{len(samples)}h", *samples)


def listening_chime(rate: int = 16000) -> bytes:
    """Two-note ascending chime — soft and modern."""
    note1 = _generate_tone(880, 0.08, volume=0.2, rate=rate)     # A5
    gap = b"\x00\x00" * int(rate * 0.03)                          # 30ms silence
    note2 = _generate_tone(1175, 0.10, volume=0.25, rate=rate)   # D6
    return note1 + gap + note2


def stop_chime(rate: int = 16000) -> bytes:
    """Single descending soft tone."""
    return _generate_tone(784, 0.09, volume=0.18, rate=rate)      # G5
