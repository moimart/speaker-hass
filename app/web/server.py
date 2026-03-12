"""FastAPI web server with WebSocket for real-time status."""

import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import Config
from app.events import EventBus

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class WebServer:
    """Web UI server with WebSocket push for state updates."""

    def __init__(self, config: Config, event_bus: EventBus) -> None:
        self.config = config
        self.event_bus = event_bus
        self._clients: set[WebSocket] = set()
        self._last_state: dict = {"state": "idle", "label": "Ready", "connected": False}
        self._last_transcript: str = ""
        self._transcript_history: list[dict] = []

    def create_app(self) -> FastAPI:
        app = FastAPI(title="Speaker HASS", docs_url=None, redoc_url=None)

        # Subscribe to events
        self.event_bus.subscribe("state.changed", self._on_state_changed)
        self.event_bus.subscribe("transcript.received", self._on_transcript)
        self.event_bus.subscribe("wakeword.detected", self._on_wakeword)

        @app.get("/", response_class=HTMLResponse)
        async def index():
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/settings", response_class=HTMLResponse)
        async def settings():
            return FileResponse(STATIC_DIR / "settings.html")

        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await ws.accept()
            self._clients.add(ws)
            try:
                # Send current state on connect
                await ws.send_json({
                    "type": "init",
                    "state": self._last_state,
                    "transcript": self._last_transcript,
                    "history": self._transcript_history[-10:],
                })
                # Keep connection alive, handle incoming messages
                while True:
                    msg = await ws.receive_text()
                    data = json.loads(msg)
                    if data.get("type") == "trigger":
                        await self.event_bus.publish("wakeword.detected", {
                            "name": "manual",
                            "score": 1.0,
                        })
            except WebSocketDisconnect:
                pass
            except Exception:
                logger.debug("WebSocket error", exc_info=True)
            finally:
                self._clients.discard(ws)

        @app.get("/api/status")
        async def status():
            return {
                "state": self._last_state,
                "transcript": self._last_transcript,
                "history": self._transcript_history[-10:],
                "config": {
                    "satellite_name": self.config.satellite_name,
                    "wake_word": self.config.wake_word_name,
                    "ha_host": self.config.ha_host,
                    "ha_port": self.config.ha_port,
                },
            }

        return app

    async def _broadcast(self, message: dict) -> None:
        """Send a message to all connected WebSocket clients."""
        dead: set[WebSocket] = set()
        for ws in self._clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def _on_state_changed(self, _event: str, data: dict) -> None:
        self._last_state = data
        await self._broadcast({"type": "state", **data})

    async def _on_transcript(self, _event: str, data: dict) -> None:
        self._last_transcript = data.get("text", "")
        entry = {"text": self._last_transcript}
        self._transcript_history.append(entry)
        if len(self._transcript_history) > 50:
            self._transcript_history = self._transcript_history[-50:]
        await self._broadcast({"type": "transcript", **data})

    async def _on_wakeword(self, _event: str, data: dict) -> None:
        await self._broadcast({"type": "wakeword", **data})
