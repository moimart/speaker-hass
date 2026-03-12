"""Tests for configuration."""

import os

from app.config import Config


def test_defaults():
    config = Config()

    assert config.satellite_port == 10700
    assert config.satellite_name == "Speaker HASS"
    assert config.audio_rate == 16000
    assert config.audio_width == 2
    assert config.audio_channels == 1
    assert config.wake_word_name == "okay_nabu"
    assert config.web_port == 8080


def test_chunk_properties():
    config = Config()

    # 30ms at 16kHz = 480 samples
    assert config.chunk_samples == 480
    # 480 samples * 2 bytes * 1 channel = 960 bytes
    assert config.chunk_bytes == 960


def test_env_override(monkeypatch):
    monkeypatch.setenv("SATELLITE_NAME", "Kitchen Speaker")
    monkeypatch.setenv("SATELLITE_PORT", "10800")
    monkeypatch.setenv("WAKE_WORD_NAME", "hey_jarvis")
    monkeypatch.setenv("WEB_PORT", "9090")

    config = Config()

    assert config.satellite_name == "Kitchen Speaker"
    assert config.satellite_port == 10800
    assert config.wake_word_name == "hey_jarvis"
    assert config.web_port == 9090
