"""ASR utilities powered by faster-whisper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from faster_whisper import WhisperModel


@dataclass(slots=True)
class WhisperConfig:
    """Configuration for the faster-whisper engine."""

    model_path: Path
    device: str = "cuda"
    compute_type: str = "float16"


class FasterWhisperEngine:
    """Thin wrapper around WhisperModel."""

    def __init__(self, config: WhisperConfig) -> None:
        self.config = config
        self.model = WhisperModel(
            str(config.model_path),
            device=config.device,
            compute_type=config.compute_type,
        )

    def transcribe(self, audio: Iterable[float]) -> str:
        """Transcribe an audio stream into text."""
        segments, _ = self.model.transcribe(audio, language="fr")
        return " ".join(segment.text for segment in segments)
