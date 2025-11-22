from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from app.core.config import get_settings

try:
    from faster_whisper import WhisperModel  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    WhisperModel = None  # type: ignore[assignment]


class ASRUnavailableError(RuntimeError):
    """Raised when the ASR backend cannot be initialised."""


class FasterWhisperASR:
    """Thin wrapper around faster-whisper for PCM16 audio."""

    def __init__(self, model_path: Path, device: str, compute_type: str) -> None:
        if WhisperModel is None:  # pragma: no cover
            raise ASRUnavailableError(
                "Le paquet faster-whisper n'est pas installé sur le serveur."
            )
        if not model_path.exists():
            raise ASRUnavailableError(f"Modèle ASR introuvable: {model_path}")
        self._model = WhisperModel(
            str(model_path),
            device=device,
            compute_type=compute_type,
        )

    def transcribe_pcm16(
        self,
        pcm_data: bytes,
        sample_rate: int,
        *,
        language: str = "fr",
        trim_silence: bool = True,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Transcribe raw PCM16 audio and return the text plus segment metadata."""
        if not pcm_data:
            return "", []
        audio = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
        if not len(audio):
            return "", []
        if trim_silence:
            audio = self._trim_silence(audio)
            if not len(audio):
                return "", []

        segments, _info = self._model.transcribe(
            audio,
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250},
        )

        transcript_parts: list[str] = []
        details: list[dict[str, Any]] = []

        for segment in segments:
            text = segment.text.strip()
            if text:
                transcript_parts.append(text)
            details.append(
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "confidence": getattr(segment, "avg_log_prob", None),
                }
            )
        transcript = " ".join(transcript_parts).strip()
        return transcript, details

    @staticmethod
    def _trim_silence(samples: np.ndarray, threshold: float = 0.01) -> np.ndarray:
        """Remove leading/trailing silence to speed up inference."""
        if samples.size == 0:
            return samples
        mask = np.abs(samples) > threshold
        indices = np.where(mask)[0]
        if indices.size == 0:
            return np.array([], dtype=samples.dtype)
        start = max(int(indices[0]) - 1600, 0)
        end = min(int(indices[-1]) + 1600, samples.size)
        return samples[start:end]


def _default_model_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "desktop" / "voice_client" / "resources" / "models" / "asr" / "faster-whisper-large-v3"


@lru_cache()
def get_asr_engine() -> FasterWhisperASR:
    """Return a cached ASR engine instance."""
    settings = get_settings()

    model_path = (
        Path(settings.voice_asr_model_path)
        if settings.voice_asr_model_path
        else _default_model_path()
    )
    return FasterWhisperASR(
        model_path=model_path,
        device=settings.voice_asr_device,
        compute_type=settings.voice_asr_compute_type,
    )
