"""Audio capture module for IVY Voice."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Iterable, Protocol

import sounddevice as sd

from .vad import VoiceActivityDetector

LOGGER = logging.getLogger(__name__)


class FrameConsumer(Protocol):
    """Protocol for streaming audio frames."""

    def __call__(self, frame: bytes) -> None: ...


@dataclass(slots=True)
class CaptureConfig:
    """Microphone capture configuration."""

    sample_rate: int = 16_000
    channels: int = 1
    frame_duration_ms: int = 20
    device_name: str | None = None
    deliver_silence: bool = False


class MicrophoneCapture:
    """High level microphone controller."""

    def __init__(
        self,
        config: CaptureConfig | None = None,
        vad: VoiceActivityDetector | None = None,
    ) -> None:
        self.config = config or CaptureConfig()
        self.vad = vad or VoiceActivityDetector()
        self._consumer: Callable[[bytes], None] | None = None
        self._stream: sd.RawInputStream | None = None
        self._lock = Lock()
        self._running = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def bind(self, consumer: FrameConsumer) -> None:
        """Register the frame consumer."""
        self._consumer = consumer

    def available_devices(self) -> Iterable[str]:
        """List available input devices."""
        return [
            device["name"]
            for device in sd.query_devices()
            if int(device.get("max_input_channels", 0)) > 0
        ]

    def start(self) -> None:
        """Start microphone capture."""
        if self._consumer is None:
            raise RuntimeError("No audio consumer registered.")
        with self._lock:
            if self._running:
                return
            frame_size = int(self.config.sample_rate * self.config.frame_duration_ms / 1000)
            self._stream = sd.RawInputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype="int16",
                blocksize=frame_size,
                callback=self._on_frame,
                device=self.config.device_name,
            )
            self._stream.start()
            self._running = True
            LOGGER.debug("Microphone capture started.")

    def stop(self) -> None:
        """Stop microphone capture."""
        with self._lock:
            if not self._running:
                return
            assert self._stream is not None
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self._running = False
            LOGGER.debug("Microphone capture stopped.")

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _on_frame(self, indata: bytes, frames: int, time, status) -> None:  # type: ignore[override]  # noqa: ANN401
        if status:  # pragma: no cover
            LOGGER.warning("Microphone status: %s", status)
        frame = bytes(indata)
        if self.vad and not self.vad.is_speech(frame, self.config.sample_rate):
            if not self.config.deliver_silence:
                return
        if self._consumer is not None:
            self._consumer(frame)
