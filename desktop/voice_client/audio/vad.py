"""Voice activity detection utilities."""

from __future__ import annotations

from dataclasses import dataclass

import webrtcvad


_VALID_SAMPLE_RATES = (8000, 16_000, 32_000, 48_000)
_VALID_FRAME_DURATIONS_MS = (10, 20, 30)


@dataclass(slots=True)
class VADConfig:
    """WebRTC VAD configuration."""

    aggressiveness: int = 2  # 0 (sensitive) to 3 (strict)


class VoiceActivityDetector:
    """Wrapper around the WebRTC VAD implementation."""

    def __init__(self, config: VADConfig | None = None) -> None:
        self.config = config or VADConfig()
        self._vad = webrtcvad.Vad(self.config.aggressiveness)

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        """Return True when the frame contains speech."""
        normalized = self._normalize_frame(frame, sample_rate)
        return self._vad.is_speech(normalized, sample_rate)

    def update_aggressiveness(self, value: int) -> None:
        """Update aggressiveness level."""
        self.config.aggressiveness = max(0, min(3, value))
        self._vad.set_mode(self.config.aggressiveness)

    @staticmethod
    def _bytes_per_sample() -> int:
        """Mono PCM_s16le uses 2 bytes per sample."""
        return 2

    @classmethod
    def _normalize_frame(cls, frame: bytes, sample_rate: int) -> bytes:
        """Pad or trim frames so that WebRTC VAD accepts them."""
        if not frame or sample_rate not in _VALID_SAMPLE_RATES:
            return frame

        bytes_per_sample = cls._bytes_per_sample()
        frame_samples = len(frame) // bytes_per_sample
        if frame_samples == 0:
            return frame

        expected_samples = [
            sample_rate * duration // 1000 for duration in _VALID_FRAME_DURATIONS_MS
        ]
        target_samples = min(expected_samples, key=lambda expected: abs(expected - frame_samples))
        target_samples = max(target_samples, 1)
        target_bytes = target_samples * bytes_per_sample

        if len(frame) == target_bytes:
            return frame
        if len(frame) > target_bytes:
            return frame[:target_bytes]
        padding = bytes(target_bytes - len(frame))
        return frame + padding
