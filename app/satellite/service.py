"""Wyoming satellite service — connects to Home Assistant voice pipeline."""

import asyncio
import io
import logging
import wave

from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event, async_read_event, async_write_event
from wyoming.info import Attribution, Describe, Info, Satellite
from wyoming.ping import Ping, Pong
from wyoming.pipeline import PipelineStage, RunPipeline
from wyoming.satellite import RunSatellite, StreamingStarted, StreamingStopped
from wyoming.vad import VoiceStarted, VoiceStopped
from wyoming.wake import Detect, Detection

from app.audio.player import AudioPlayer
from app.audio.sounds import listening_chime
from app.config import Config
from app.events import EventBus
from app.satellite.state import SatelliteState

logger = logging.getLogger(__name__)


class SatelliteService:
    """Manages the Wyoming satellite protocol connection to Home Assistant."""

    def __init__(self, config: Config, event_bus: EventBus, player: AudioPlayer) -> None:
        self.config = config
        self.event_bus = event_bus
        self.player = player
        self._state = SatelliteState.IDLE
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._streaming = False
        self._tts_audio: list[bytes] = []
        self._tts_rate = 0
        self._tts_width = 0
        self._tts_channels = 0
        self._connected = False
        self._transcript_text = ""
        self._chunk_count = 0

    @property
    def state(self) -> SatelliteState:
        return self._state

    @property
    def connected(self) -> bool:
        return self._connected

    async def stop_listening(self) -> None:
        """Stop streaming audio to HA (triggered from UI)."""
        logger.info("Stop listening requested (streaming=%s, chunks_sent=%d)", self._streaming, self._chunk_count)
        if self._streaming:
            self._streaming = False
            await self._send_event(AudioStop(timestamp=0).event())
            logger.info("Sent AudioStop to HA")
            await self._set_state(SatelliteState.PROCESSING)
        else:
            logger.warning("Stop requested but not currently streaming")

    async def run(self) -> None:
        """Run the satellite: listen for HA connections on our TCP port."""
        self.event_bus.subscribe("wakeword.detected", self._on_wakeword)
        self.event_bus.subscribe("audio.chunk", self._on_audio_chunk)
        self.event_bus.subscribe("listening.stop", self._on_stop_listening)

        server = await asyncio.start_server(
            self._handle_connection,
            "0.0.0.0",
            self.config.satellite_port,
        )
        logger.info("Wyoming satellite listening on port %d", self.config.satellite_port)

        async with server:
            await server.serve_forever()

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a connection from Home Assistant."""
        peer = writer.get_extra_info("peername")
        logger.info("Home Assistant connected from %s", peer)

        self._reader = reader
        self._writer = writer
        self._connected = True
        await self._set_state(SatelliteState.IDLE)

        try:
            while True:
                event = await async_read_event(reader)
                if event is None:
                    break
                await self._handle_event(event)
        except (ConnectionResetError, asyncio.IncompleteReadError):
            logger.warning("Connection lost from %s", peer)
        except Exception:
            logger.exception("Error handling connection from %s", peer)
        finally:
            self._connected = False
            self._streaming = False
            self._writer = None
            self._reader = None
            writer.close()
            await self._set_state(SatelliteState.ERROR)
            logger.info("Home Assistant disconnected")

    async def _handle_event(self, event: Event) -> None:
        """Process an incoming Wyoming event from HA."""
        logger.info("Received event: %s", event.type)
        if Describe.is_type(event.type):
            await self._send_info()

        elif RunSatellite.is_type(event.type):
            logger.info("RunSatellite received — ready for wake words")
            await self._set_state(SatelliteState.IDLE)

        elif StreamingStarted.is_type(event.type):
            logger.info("HA pipeline started — streaming audio")
            self._streaming = True
            await self._set_state(SatelliteState.LISTENING)

        elif StreamingStopped.is_type(event.type):
            logger.info("HA pipeline stopped streaming")
            self._streaming = False
            await self._set_state(SatelliteState.PROCESSING)

        elif Transcript.is_type(event.type):
            transcript = Transcript.from_event(event)
            self._transcript_text = transcript.text
            logger.info("Transcript: %s", transcript.text)
            await self.event_bus.publish("transcript.received", {
                "text": transcript.text,
            })

        elif AudioStart.is_type(event.type):
            audio_start = AudioStart.from_event(event)
            self._tts_audio = []
            self._tts_rate = audio_start.rate
            self._tts_width = audio_start.width
            self._tts_channels = audio_start.channels
            await self._set_state(SatelliteState.RESPONDING)

        elif AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            self._tts_audio.append(chunk.audio)

        elif AudioStop.is_type(event.type):
            if self._tts_audio:
                logger.info("Playing TTS response (%d chunks)", len(self._tts_audio))
                await self.player.play_chunks(
                    self._tts_audio,
                    rate=self._tts_rate,
                    width=self._tts_width,
                    channels=self._tts_channels,
                )
                self._tts_audio = []
            # Notify HA that we finished playing
            await self._send_event(
                AudioStop(timestamp=0).event()
            )
            await self._set_state(SatelliteState.IDLE)

        elif RunPipeline.is_type(event.type):
            pipeline = RunPipeline.from_event(event)
            if pipeline.start_stage == PipelineStage.TTS:
                # Announcement from HA automation
                logger.info("Announcement pipeline: %s", pipeline.announce_text or "(audio)")
                if pipeline.announce_text:
                    await self.event_bus.publish("announcement.received", {
                        "text": pipeline.announce_text,
                    })
                await self._set_state(SatelliteState.RESPONDING)
            else:
                logger.info("RunPipeline: %s → %s", pipeline.start_stage.value, pipeline.end_stage.value)

        elif Detect.is_type(event.type):
            logger.debug("Detect received — listening for wake word")
            await self._set_state(SatelliteState.IDLE)

        elif Ping.is_type(event.type):
            ping = Ping.from_event(event)
            await self._send_event(Pong(text=ping.text).event())

        else:
            logger.warning("Unhandled event type: %s (data=%s)", event.type, event.data)

    async def _send_info(self) -> None:
        """Send satellite info to HA."""
        info = Info(
            satellite=Satellite(
                name=self.config.satellite_name,
                description="Speaker HASS Voice Satellite",
                version="1.0.0",
                attribution=Attribution(
                    name="Speaker HASS",
                    url="",
                ),
                installed=True,
            )
        )
        await self._send_event(info.event())

    async def _on_wakeword(self, _event: str, data: dict) -> None:
        """Handle wake word detection — notify HA."""
        if not self._connected or self._writer is None:
            logger.warning("Wake word detected but not connected to HA")
            return

        await self._set_state(SatelliteState.WAKE_DETECTED)

        detection = Detection(
            name=data.get("name", self.config.wake_word_name),
            timestamp=0,
        )
        await self._send_event(detection.event())
        logger.info("Sent wake word detection to HA")

        # Tell HA to start the ASR → TTS pipeline (required for local wake word)
        await self._send_event(
            RunPipeline(
                start_stage=PipelineStage.ASR,
                end_stage=PipelineStage.TTS,
            ).event()
        )
        logger.info("Sent RunPipeline (ASR→TTS) to HA")

        # Play listening chime
        if self.config.sound_enabled:
            await self.player.play(listening_chime(self.config.audio_rate))

        # Start streaming audio
        self._chunk_count = 0
        await self._send_event(
            AudioStart(
                rate=self.config.audio_rate,
                width=self.config.audio_width,
                channels=self.config.audio_channels,
                timestamp=0,
            ).event()
        )
        self._streaming = True
        await self._set_state(SatelliteState.LISTENING)

    async def _on_audio_chunk(self, _event: str, data: bytes) -> None:
        """Forward mic audio to HA when streaming."""
        if not self._streaming or self._writer is None:
            return

        self._chunk_count += 1
        if self._chunk_count % 50 == 1:
            # Log every 50 chunks (~1.6s at 16kHz/512 samples)
            # Calculate RMS to check if mic is actually capturing audio
            import struct
            samples = struct.unpack(f"<{len(data)//2}h", data)
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
            logger.info(
                "Audio chunk #%d: %d bytes, RMS=%.0f (streaming=%s)",
                self._chunk_count, len(data), rms, self._streaming,
            )

        chunk = AudioChunk(
            audio=data,
            rate=self.config.audio_rate,
            width=self.config.audio_width,
            channels=self.config.audio_channels,
            timestamp=0,
        )
        await self._send_event(chunk.event())

    async def _on_stop_listening(self, _event: str, _data: dict) -> None:
        """Handle stop listening request from UI."""
        await self.stop_listening()

    async def _send_event(self, event: Event) -> None:
        """Send a Wyoming event to HA."""
        if self._writer is None:
            return
        try:
            await async_write_event(event, self._writer)
        except (ConnectionResetError, BrokenPipeError):
            logger.warning("Failed to send event — connection lost")
            self._connected = False
            self._streaming = False

    async def _set_state(self, state: SatelliteState) -> None:
        """Update the satellite state and notify listeners."""
        old_state = self._state
        self._state = state
        if old_state != state:
            logger.info("State: %s -> %s", old_state.value, state.value)
            await self.event_bus.publish("state.changed", {
                "state": state.value,
                "previous": old_state.value,
                "label": state.label,
                "connected": self._connected,
            })
