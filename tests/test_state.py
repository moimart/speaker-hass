"""Tests for satellite state machine."""

from app.satellite.state import SatelliteState


def test_state_values():
    assert SatelliteState.IDLE == "idle"
    assert SatelliteState.WAKE_DETECTED == "wake"
    assert SatelliteState.LISTENING == "listening"
    assert SatelliteState.PROCESSING == "processing"
    assert SatelliteState.RESPONDING == "responding"
    assert SatelliteState.ERROR == "error"


def test_state_labels():
    assert SatelliteState.IDLE.label == "Ready"
    assert SatelliteState.WAKE_DETECTED.label == "Wake Word Detected"
    assert SatelliteState.LISTENING.label == "Listening"
    assert SatelliteState.PROCESSING.label == "Processing"
    assert SatelliteState.RESPONDING.label == "Speaking"
    assert SatelliteState.ERROR.label == "Error"


def test_state_is_string():
    # SatelliteState inherits from str, so it can be used directly in dicts/JSON
    assert isinstance(SatelliteState.IDLE, str)
    assert f"state={SatelliteState.IDLE.value}" == "state=idle"
