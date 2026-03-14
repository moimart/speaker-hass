"""Tests for the sendspin media player service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Config
from app.events import EventBus
from app.media.service import MediaPlayerService, _extract_card_name, find_portaudio_device


@pytest.fixture
def media_player(config, event_bus):
    return MediaPlayerService(config, event_bus)


# --- Card name extraction ---


def test_extract_card_name_standard():
    assert _extract_card_name("plughw:CARD=S330,DEV=0") == "S330"


def test_extract_card_name_jabra():
    assert _extract_card_name("plughw:CARD=Jabra,DEV=0") == "Jabra"


def test_extract_card_name_no_match():
    assert _extract_card_name("default") == ""


def test_extract_card_name_empty():
    assert _extract_card_name("") == ""


# --- PortAudio device detection ---


def test_find_portaudio_device_match():
    fake_devices = [
        {"name": "Built-in Audio", "max_output_channels": 2},
        {"name": "Anker PowerConf S330: USB Audio", "max_output_channels": 2},
        {"name": "HDMI Output", "max_output_channels": 8},
    ]
    with patch("sounddevice.query_devices", return_value=fake_devices):
        idx = find_portaudio_device("S330")
    assert idx == 1


def test_find_portaudio_device_no_match():
    fake_devices = [
        {"name": "Built-in Audio", "max_output_channels": 2},
    ]
    with patch("sounddevice.query_devices", return_value=fake_devices):
        idx = find_portaudio_device("S330")
    assert idx == -1


def test_find_portaudio_device_empty_card():
    idx = find_portaudio_device("")
    assert idx == -1


def test_find_portaudio_device_sounddevice_unavailable():
    with patch("builtins.__import__", side_effect=ImportError):
        idx = find_portaudio_device("S330")
    assert idx == -1


def test_find_portaudio_device_skips_input_only():
    fake_devices = [
        {"name": "S330 Microphone", "max_output_channels": 0},
        {"name": "S330 Speaker", "max_output_channels": 2},
    ]
    with patch("sounddevice.query_devices", return_value=fake_devices):
        idx = find_portaudio_device("S330")
    assert idx == 1


# --- Pause/resume on state changes ---


@pytest.mark.asyncio
async def test_stops_sendspin_when_responding(media_player, event_bus):
    """Sendspin process should be stopped when voice assistant starts responding."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)

    mock_proc = MagicMock()
    mock_proc.returncode = None
    media_player._process = mock_proc

    with patch.object(media_player, "_stop_process", new_callable=AsyncMock) as mock_stop:
        await event_bus.publish("state.changed", {
            "state": "responding",
            "previous": "processing",
            "label": "Responding",
            "connected": True,
        })

        mock_stop.assert_called_once()
        assert media_player._was_playing is True


@pytest.mark.asyncio
async def test_stops_sendspin_on_wake(media_player, event_bus):
    """Sendspin should also stop on wake word detection."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)

    mock_proc = MagicMock()
    mock_proc.returncode = None
    media_player._process = mock_proc

    with patch.object(media_player, "_stop_process", new_callable=AsyncMock) as mock_stop:
        await event_bus.publish("state.changed", {
            "state": "wake",
            "previous": "idle",
            "label": "Wake",
            "connected": True,
        })

        mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_resets_flag_on_idle(media_player, event_bus):
    """_was_playing flag should be reset when returning to idle."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)
    media_player._was_playing = True

    await event_bus.publish("state.changed", {
        "state": "idle",
        "previous": "responding",
        "label": "Ready",
        "connected": True,
    })

    assert media_player._was_playing is False


@pytest.mark.asyncio
async def test_no_stop_if_process_already_exited(media_player, event_bus):
    """Should not try to stop a process that has already exited."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)

    mock_proc = MagicMock()
    mock_proc.returncode = 0  # already exited
    media_player._process = mock_proc

    with patch.object(media_player, "_stop_process", new_callable=AsyncMock) as mock_stop:
        await event_bus.publish("state.changed", {
            "state": "responding",
            "previous": "processing",
            "label": "Responding",
            "connected": True,
        })

        mock_stop.assert_not_called()


@pytest.mark.asyncio
async def test_ignores_irrelevant_states(media_player, event_bus):
    """Should not stop for listening/processing/error states."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)

    mock_proc = MagicMock()
    mock_proc.returncode = None
    media_player._process = mock_proc

    with patch.object(media_player, "_stop_process", new_callable=AsyncMock) as mock_stop:
        for state in ("listening", "processing", "error"):
            await event_bus.publish("state.changed", {
                "state": state,
                "previous": "idle",
                "label": state,
                "connected": True,
            })

        mock_stop.assert_not_called()


# --- MA host config ---


def test_ma_host_from_env(config, event_bus):
    with patch.dict("os.environ", {"MUSIC_ASSISTANT_HOST": "10.20.30.5"}):
        svc = MediaPlayerService(config, event_bus)
        assert svc._ma_host == "10.20.30.5"


def test_ma_host_defaults_empty(config, event_bus):
    with patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("MUSIC_ASSISTANT_HOST", None)
        svc = MediaPlayerService(config, event_bus)
        assert svc._ma_host == ""
