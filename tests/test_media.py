"""Tests for the media player service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Config
from app.events import EventBus
from app.media.service import MediaPlayerService, MPD_CONF_TEMPLATE


@pytest.fixture
def media_player(config, event_bus):
    return MediaPlayerService(config, event_bus)


# --- Config generation ---


def test_mpd_conf_template_includes_device(config):
    conf = MPD_CONF_TEMPLATE.format(
        snd_device=config.snd_device,
        mpd_port=6600,
    )
    assert config.snd_device in conf
    assert '"6600"' in conf


def test_mpd_conf_template_includes_curl_input(config):
    conf = MPD_CONF_TEMPLATE.format(
        snd_device=config.snd_device,
        mpd_port=6600,
    )
    assert 'plugin      "curl"' in conf


# --- Pause/resume on state changes ---


@pytest.mark.asyncio
async def test_pauses_mpd_when_responding(media_player, event_bus):
    """MPD should pause when voice assistant starts responding."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)

    with patch.object(media_player, "_is_playing", return_value=True):
        with patch.object(media_player, "_mpc", new_callable=AsyncMock) as mock_mpc:
            await event_bus.publish("state.changed", {
                "state": "responding",
                "previous": "processing",
                "label": "Responding",
                "connected": True,
            })

            mock_mpc.assert_called_once_with("pause")
            assert media_player._was_playing is True


@pytest.mark.asyncio
async def test_resumes_mpd_when_idle_after_pause(media_player, event_bus):
    """MPD should resume when voice assistant goes idle after being paused."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)
    media_player._was_playing = True

    with patch.object(media_player, "_mpc", new_callable=AsyncMock) as mock_mpc:
        await event_bus.publish("state.changed", {
            "state": "idle",
            "previous": "responding",
            "label": "Ready",
            "connected": True,
        })

        mock_mpc.assert_called_once_with("play")
        assert media_player._was_playing is False


@pytest.mark.asyncio
async def test_no_resume_if_was_not_playing(media_player, event_bus):
    """MPD should not resume if it wasn't playing before the interruption."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)
    media_player._was_playing = False

    with patch.object(media_player, "_mpc", new_callable=AsyncMock) as mock_mpc:
        await event_bus.publish("state.changed", {
            "state": "idle",
            "previous": "responding",
            "label": "Ready",
            "connected": True,
        })

        mock_mpc.assert_not_called()


@pytest.mark.asyncio
async def test_no_pause_if_not_playing(media_player, event_bus):
    """MPD should not pause if it wasn't playing."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)

    with patch.object(media_player, "_is_playing", return_value=False):
        with patch.object(media_player, "_mpc", new_callable=AsyncMock) as mock_mpc:
            await event_bus.publish("state.changed", {
                "state": "responding",
                "previous": "processing",
                "label": "Responding",
                "connected": True,
            })

            mock_mpc.assert_not_called()
            assert media_player._was_playing is False


@pytest.mark.asyncio
async def test_pauses_on_wake_state(media_player, event_bus):
    """MPD should also pause on wake word detection."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)

    with patch.object(media_player, "_is_playing", return_value=True):
        with patch.object(media_player, "_mpc", new_callable=AsyncMock) as mock_mpc:
            await event_bus.publish("state.changed", {
                "state": "wake",
                "previous": "idle",
                "label": "Wake",
                "connected": True,
            })

            mock_mpc.assert_called_once_with("pause")


@pytest.mark.asyncio
async def test_ignores_irrelevant_states(media_player, event_bus):
    """MPD should not react to listening or processing states."""
    event_bus.subscribe("state.changed", media_player._on_state_changed)

    with patch.object(media_player, "_is_playing", return_value=True):
        with patch.object(media_player, "_mpc", new_callable=AsyncMock) as mock_mpc:
            for state in ("listening", "processing", "error"):
                await event_bus.publish("state.changed", {
                    "state": state,
                    "previous": "idle",
                    "label": state,
                    "connected": True,
                })

            mock_mpc.assert_not_called()


# --- Default port ---


def test_default_mpd_port(config, event_bus):
    with patch.dict("os.environ", {}, clear=False):
        svc = MediaPlayerService(config, event_bus)
        assert svc._mpd_port == 6600
