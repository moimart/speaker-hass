"""FastAPI web server with WebSocket for real-time status."""

import asyncio
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
        self.event_bus.subscribe("announcement.received", self._on_announcement)

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
                    elif data.get("type") == "stop_listening":
                        await self.event_bus.publish("listening.stop", {})
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
                    "satellite_port": self.config.satellite_port,
                    "wake_word": self.config.wake_word_name,
                },
            }

        @app.get("/api/volume")
        async def get_volume():
            vol = await self._get_alsa_volume()
            return {"volume": vol}

        @app.post("/api/volume/{level}")
        async def set_volume(level: int):
            level = max(0, min(100, level))
            await self._set_alsa_volume(level)
            return {"volume": level}

        @app.get("/api/mute")
        async def get_mute():
            muted = await self._get_mic_mute()
            return {"muted": muted}

        @app.post("/api/mute/toggle")
        async def toggle_mute():
            muted = await self._get_mic_mute()
            await self._set_mic_mute(not muted)
            return {"muted": not muted}

        return app

    async def _discover_volume_control(self) -> str | None:
        """Find the ALSA playback volume control name from the configured sound device."""
        if hasattr(self, "_volume_control"):
            return self._volume_control

        # Extract card name from device string like "plughw:CARD=S330,DEV=0"
        card_arg = []
        snd = self.config.snd_device
        if "CARD=" in snd:
            card = snd.split("CARD=")[1].split(",")[0]
            card_arg = ["-c", card]

        try:
            proc = await asyncio.create_subprocess_exec(
                "amixer", *card_arg, "scontrols",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                self._volume_control = None
                return None

            # Find a playback volume control
            import re
            for line in stdout.decode().splitlines():
                name_match = re.search(r"'(.+?)'", line)
                if name_match:
                    name = name_match.group(1)
                    # Check if this control has playback volume
                    proc2 = await asyncio.create_subprocess_exec(
                        "amixer", *card_arg, "get", name,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    out2, _ = await proc2.communicate()
                    text = out2.decode()
                    if "Playback" in text and "%" in text:
                        self._volume_control = name
                        self._volume_card_arg = card_arg
                        logger.info("Discovered volume control: %s (card: %s)", name, card_arg)
                        return name

            self._volume_control = None
            return None
        except Exception:
            self._volume_control = None
            return None

    async def _get_alsa_volume(self) -> int:
        """Read current ALSA playback volume (0-100)."""
        control = await self._discover_volume_control()
        if not control:
            return 50
        try:
            proc = await asyncio.create_subprocess_exec(
                "amixer", *self._volume_card_arg, "get", control,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            import re
            match = re.search(r"\[(\d+)%\]", stdout.decode())
            return int(match.group(1)) if match else 50
        except Exception:
            return 50

    async def _set_alsa_volume(self, level: int) -> None:
        """Set ALSA playback volume (0-100)."""
        control = await self._discover_volume_control()
        if not control:
            return
        await asyncio.create_subprocess_exec(
            "amixer", *self._volume_card_arg, "set", control, f"{level}%",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def _discover_capture_switch(self) -> int | None:
        """Find the ALSA capture switch numid from the configured mic device."""
        if hasattr(self, "_capture_switch_numid"):
            return self._capture_switch_numid

        card_arg = []
        mic = self.config.mic_device
        if "CARD=" in mic:
            card = mic.split("CARD=")[1].split(",")[0]
            card_arg = ["-c", card]

        try:
            proc = await asyncio.create_subprocess_exec(
                "amixer", *card_arg, "controls",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                self._capture_switch_numid = None
                return None

            import re
            for line in stdout.decode().splitlines():
                if "Capture Switch" in line:
                    match = re.search(r"numid=(\d+)", line)
                    if match:
                        self._capture_switch_numid = int(match.group(1))
                        self._capture_card_arg = card_arg
                        logger.info("Discovered capture switch: numid=%d", self._capture_switch_numid)
                        return self._capture_switch_numid

            self._capture_switch_numid = None
            return None
        except Exception:
            self._capture_switch_numid = None
            return None

    async def _get_mic_mute(self) -> bool:
        """Check if mic is muted (capture switch off)."""
        numid = await self._discover_capture_switch()
        if numid is None:
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                "amixer", *self._capture_card_arg, "cget", f"numid={numid}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return "values=off" in stdout.decode()
        except Exception:
            return False

    async def _set_mic_mute(self, mute: bool) -> None:
        """Set mic mute state."""
        numid = await self._discover_capture_switch()
        if numid is None:
            return
        await asyncio.create_subprocess_exec(
            "amixer", *self._capture_card_arg, "cset", f"numid={numid}", "0" if mute else "1",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

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

    async def _on_announcement(self, _event: str, data: dict) -> None:
        text = data.get("text", "")
        if text:
            entry = {"text": f"📢 {text}"}
            self._transcript_history.append(entry)
            if len(self._transcript_history) > 50:
                self._transcript_history = self._transcript_history[-50:]
        await self._broadcast({"type": "announcement", **data})
