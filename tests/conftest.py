"""Shared fixtures for tests."""

import pytest

from app.config import Config
from app.events import EventBus


@pytest.fixture
def config():
    """Config with test defaults."""
    return Config()


@pytest.fixture
def event_bus():
    """Fresh event bus for each test."""
    return EventBus()
