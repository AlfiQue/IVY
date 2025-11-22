"""Text-to-speech helpers using Piper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unicodedata

from piper import PiperVoice, SynthesisConfig


@dataclass(slots=True)
class PiperConfig:
    """Piper model configuration."""

    model_path: Path
    config_path: Path
    speaker_id: int | None = None
    length_scale: float = 1.0
    noise_scale: float = 0.85


class PiperTTS:
    """Thin wrapper around PiperVoice."""

    def __init__(self, config: PiperConfig) -> None:
        self.config = config
        self._voice = self._load_voice(config)

    def synthesize(self, text: str) -> tuple[bytes, int]:
        """Generate PCM audio for the given text."""
        text = self._sanitize_text(text)
        if not text.strip():
            return b"", 0
        pcm_bytes = b""
        sample_rate = 0
        for chunk, rate, _channels in self.synthesize_stream(text):
            sample_rate = rate
            pcm_bytes += chunk
        return pcm_bytes, sample_rate

    def synthesize_stream(self, text: str):
        """Yield audio chunks (bytes, sample_rate, channels)."""
        text = self._sanitize_text(text)
        if not text.strip():
            return
        kwargs = {}
        if self.config.speaker_id is not None:
            kwargs["speaker_id"] = self.config.speaker_id
        if self.config.length_scale != 1.0:
            kwargs["length_scale"] = self.config.length_scale
        if self.config.noise_scale > 0:
            kwargs["noise_scale"] = self.config.noise_scale
        syn_config = SynthesisConfig(**kwargs) if kwargs else None
        for chunk in self._voice.synthesize(text, syn_config=syn_config):
            yield chunk.audio_int16_bytes, chunk.sample_rate, chunk.sample_channels or 1

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load_voice(config: PiperConfig) -> PiperVoice:
        if not config.model_path.exists():
            raise FileNotFoundError(f"Piper model not found: {config.model_path}")
        if not config.config_path.exists():
            raise FileNotFoundError(f"Piper config not found: {config.config_path}")
        voice = PiperVoice.load(str(config.model_path), str(config.config_path))
        # Certaines voix FR peuvent manquer des entrées pour les tildes combinants.
        phoneme_map = dict(voice.config.phoneme_id_map)
        fallback = phoneme_map.get(" ") or phoneme_map.get("_", [0])
        if isinstance(fallback, int):
            fallback_ids = [fallback]
        else:
            fallback_ids = list(fallback) if fallback else [0]
        for missing in ("\u0303", "\u02DC", "~"):
            phoneme_map.setdefault(missing, fallback_ids)
        voice.config.phoneme_id_map = phoneme_map
        return voice

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Normalize text to avoid missing phoneme mappings."""
        normalized = unicodedata.normalize("NFD", text)
        # Supprimer les diacritiques non pris en charge (Mn) et les tildes.
        stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        cleaned = stripped.replace("\u02DC", "").replace("~", "")
        return unicodedata.normalize("NFC", cleaned)
