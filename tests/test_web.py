"""Tests for the web server and API."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Config
from app.events import EventBus
from app.web.server import WebServer


@pytest.fixture
def app(config, event_bus):
    web_server = WebServer(config, event_bus)
    return web_server.create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_index_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Speaker" in resp.text


@pytest.mark.asyncio
async def test_settings_returns_html(client):
    resp = await client.get("/settings")
    assert resp.status_code == 200
    assert "Settings" in resp.text


@pytest.mark.asyncio
async def test_api_status(client):
    resp = await client.get("/api/status")
    assert resp.status_code == 200

    data = resp.json()
    assert data["state"]["state"] == "idle"
    assert data["config"]["satellite_name"] == "Speaker HASS"
    assert data["config"]["wake_word"] == "okay_nabu"
    assert data["config"]["satellite_port"] == 10700


@pytest.mark.asyncio
async def test_api_status_reflects_state_changes(config, event_bus):
    web_server = WebServer(config, event_bus)
    app = web_server.create_app()

    # Simulate a state change
    await event_bus.publish("state.changed", {
        "state": "listening",
        "previous": "idle",
        "label": "Listening",
        "connected": True,
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status")
        data = resp.json()
        assert data["state"]["state"] == "listening"


@pytest.mark.asyncio
async def test_transcript_history(config, event_bus):
    web_server = WebServer(config, event_bus)
    app = web_server.create_app()

    await event_bus.publish("transcript.received", {"text": "turn on the lights"})
    await event_bus.publish("transcript.received", {"text": "what time is it"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status")
        data = resp.json()
        assert len(data["history"]) == 2
        assert data["history"][0]["text"] == "turn on the lights"
        assert data["transcript"] == "what time is it"


@pytest.mark.asyncio
async def test_static_css(client):
    resp = await client.get("/static/style.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_static_js(client):
    resp = await client.get("/static/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
