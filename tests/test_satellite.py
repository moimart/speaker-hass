"""Tests for the satellite service event handling."""

import asyncio

import pytest

from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.info import Describe
from wyoming.pipeline import PipelineStage, RunPipeline
from wyoming.satellite import RunSatellite, StreamingStarted, StreamingStopped
from wyoming.wake import Detect

from app.audio.player import AudioPlayer
from app.config import Config
from app.events import EventBus
from app.satellite.service import SatelliteService
from app.satellite.state import SatelliteState


@pytest.fixture
def player(config):
    return AudioPlayer(config)


@pytest.fixture
def satellite(config, event_bus, player):
    svc = SatelliteService(config, event_bus, player)
    # Simulate connected state so event handling works
    svc._connected = True
    return svc


# --- State transitions ---


@pytest.mark.asyncio
async def test_run_satellite_sets_idle(satellite):
    event = RunSatellite().event()
    await satellite._handle_event(event)

    assert satellite.state == SatelliteState.IDLE


@pytest.mark.asyncio
async def test_streaming_started_sets_listening(satellite):
    event = StreamingStarted().event()
    await satellite._handle_event(event)

    assert satellite.state == SatelliteState.LISTENING
    assert satellite._streaming is True


@pytest.mark.asyncio
async def test_streaming_stopped_sets_processing(satellite):
    satellite._streaming = True
    event = StreamingStopped().event()
    await satellite._handle_event(event)

    assert satellite.state == SatelliteState.PROCESSING
    assert satellite._streaming is False


@pytest.mark.asyncio
async def test_detect_sets_idle(satellite):
    satellite._state = SatelliteState.RESPONDING
    event = Detect().event()
    await satellite._handle_event(event)

    assert satellite.state == SatelliteState.IDLE


# --- Transcript ---


@pytest.mark.asyncio
async def test_transcript_publishes_to_event_bus(satellite, event_bus):
    received = []

    async def handler(event_type, data):
        received.append(data)

    event_bus.subscribe("transcript.received", handler)

    event = Transcript(text="turn on the lights").event()
    await satellite._handle_event(event)

    assert len(received) == 1
    assert received[0]["text"] == "turn on the lights"


# --- TTS audio collection ---


@pytest.mark.asyncio
async def test_audio_start_sets_responding(satellite):
    event = AudioStart(rate=22050, width=2, channels=1, timestamp=0).event()
    await satellite._handle_event(event)

    assert satellite.state == SatelliteState.RESPONDING
    assert satellite._tts_rate == 22050
    assert satellite._tts_audio == []


@pytest.mark.asyncio
async def test_audio_chunks_accumulated(satellite):
    await satellite._handle_event(
        AudioStart(rate=16000, width=2, channels=1, timestamp=0).event()
    )

    chunk_data = b"\x00\x01" * 100
    await satellite._handle_event(
        AudioChunk(audio=chunk_data, rate=16000, width=2, channels=1, timestamp=0).event()
    )
    await satellite._handle_event(
        AudioChunk(audio=chunk_data, rate=16000, width=2, channels=1, timestamp=0).event()
    )

    assert len(satellite._tts_audio) == 2
    assert satellite._tts_audio[0] == chunk_data


# --- Announcements ---


@pytest.mark.asyncio
async def test_announcement_pipeline_sets_responding(satellite):
    event = RunPipeline(
        start_stage=PipelineStage.TTS,
        end_stage=PipelineStage.TTS,
        announce_text="Dinner is ready",
    ).event()
    await satellite._handle_event(event)

    assert satellite.state == SatelliteState.RESPONDING


@pytest.mark.asyncio
async def test_announcement_publishes_text(satellite, event_bus):
    received = []

    async def handler(event_type, data):
        received.append(data)

    event_bus.subscribe("announcement.received", handler)

    event = RunPipeline(
        start_stage=PipelineStage.TTS,
        end_stage=PipelineStage.TTS,
        announce_text="Front door opened",
    ).event()
    await satellite._handle_event(event)

    assert len(received) == 1
    assert received[0]["text"] == "Front door opened"


@pytest.mark.asyncio
async def test_non_tts_pipeline_does_not_announce(satellite, event_bus):
    received = []

    async def handler(event_type, data):
        received.append(data)

    event_bus.subscribe("announcement.received", handler)

    event = RunPipeline(
        start_stage=PipelineStage.WAKE,
        end_stage=PipelineStage.TTS,
    ).event()
    await satellite._handle_event(event)

    assert received == []


# --- State change events ---


@pytest.mark.asyncio
async def test_state_changes_published(satellite, event_bus):
    states = []

    async def handler(event_type, data):
        states.append(data["state"])

    event_bus.subscribe("state.changed", handler)

    # Satellite starts in IDLE, so force a different state first
    satellite._state = SatelliteState.ERROR
    await satellite._handle_event(RunSatellite().event())
    await satellite._handle_event(StreamingStarted().event())
    await satellite._handle_event(StreamingStopped().event())

    assert states == ["idle", "listening", "processing"]


# --- Describe ---


@pytest.mark.asyncio
async def test_describe_does_not_crash(satellite):
    """Describe sends info back — just verify it doesn't error without a writer."""
    satellite._writer = None
    event = Describe().event()
    await satellite._handle_event(event)
    # No exception = pass
