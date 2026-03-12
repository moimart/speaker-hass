"""Tests for the async event bus."""

import pytest

from app.events import EventBus


@pytest.mark.asyncio
async def test_publish_subscribe(event_bus):
    received = []

    async def handler(event_type, data):
        received.append((event_type, data))

    event_bus.subscribe("test.event", handler)
    await event_bus.publish("test.event", {"key": "value"})

    assert len(received) == 1
    assert received[0] == ("test.event", {"key": "value"})


@pytest.mark.asyncio
async def test_multiple_subscribers(event_bus):
    results = []

    async def handler_a(event_type, data):
        results.append("a")

    async def handler_b(event_type, data):
        results.append("b")

    event_bus.subscribe("test.event", handler_a)
    event_bus.subscribe("test.event", handler_b)
    await event_bus.publish("test.event", None)

    assert results == ["a", "b"]


@pytest.mark.asyncio
async def test_no_crosstalk(event_bus):
    received = []

    async def handler(event_type, data):
        received.append(event_type)

    event_bus.subscribe("event.a", handler)
    await event_bus.publish("event.b", None)

    assert received == []


@pytest.mark.asyncio
async def test_unsubscribe(event_bus):
    received = []

    async def handler(event_type, data):
        received.append(data)

    event_bus.subscribe("test.event", handler)
    await event_bus.publish("test.event", 1)
    event_bus.unsubscribe("test.event", handler)
    await event_bus.publish("test.event", 2)

    assert received == [1]


@pytest.mark.asyncio
async def test_state_changed_tracks_current(event_bus):
    await event_bus.publish("state.changed", {"state": "listening"})

    assert event_bus.get_state("current") == {"state": "listening"}


@pytest.mark.asyncio
async def test_get_state_returns_none_for_unknown(event_bus):
    assert event_bus.get_state("nonexistent") is None


@pytest.mark.asyncio
async def test_handler_exception_does_not_break_others(event_bus):
    results = []

    async def bad_handler(event_type, data):
        raise RuntimeError("boom")

    async def good_handler(event_type, data):
        results.append(data)

    event_bus.subscribe("test.event", bad_handler)
    event_bus.subscribe("test.event", good_handler)
    await event_bus.publish("test.event", "ok")

    assert results == ["ok"]
