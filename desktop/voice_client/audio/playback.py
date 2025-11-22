"""TTS playback service for the IVY voice client."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

import sounddevice as sd


@dataclass(slots=True)
class PlaybackConfig:
    """Playback configuration."""

    sample_rate: int = 22_050
    channels: int = 1
    device_name: str | None = None


class SpeechPlayback:
    """Manage audio output for synthesized speech."""

    def __init__(self, config: PlaybackConfig | None = None) -> None:
        self.config = config or PlaybackConfig()
        self._buffer = deque[bytes]()
        self._lock = threading.RLock()
        self._stream: sd.RawOutputStream | None = None
        self._paused = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def play(self, pcm_data: bytes) -> None:
        """Queue a PCM buffer for playback."""
        if not pcm_data:
            return
        with self._lock:
            self._ensure_stream()
            self._buffer.append(pcm_data)

    def stop(self) -> None:
        """Stop playback and clear the buffer."""
        with self._lock:
            self._buffer.clear()
            self._paused = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

    def pause(self) -> None:
        """Pause playback."""
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """Resume playback."""
        with self._lock:
            if not self._paused:
                return
            self._paused = False
            if self._stream is not None and not self._stream.active:
                self._stream.start()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _ensure_stream(self) -> None:
        if self._stream is not None:
            if not self._stream.active:
                self._stream.start()
            return
        self._stream = sd.RawOutputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            callback=self._on_write,
            device=self.config.device_name,
        )
        self._stream.start()

    def _on_write(self, outdata: bytearray, frames: int, time, status) -> None:  # type: ignore[override]  # noqa: ANN401
        if status:  # pragma: no cover
            print(f"[SpeechPlayback] audio status: {status}")
        with self._lock:
            if self._paused or not self._buffer:
                outdata[:] = b"\x00" * len(outdata)
                return
            chunk = self._buffer.popleft()
            if len(chunk) >= len(outdata):
                outdata[:] = chunk[: len(outdata)]
                remainder = chunk[len(outdata) :]
                if remainder:
                    self._buffer.appendleft(remainder)
            else:
                outdata[: len(chunk)] = chunk
                outdata[len(chunk) :] = b"\x00" * (len(outdata) - len(chunk))
