"""Local configuration models for the voice client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Color = Literal["green", "orange", "red"]


@dataclass(slots=True)
class ServerSettings:
    """Connection settings for the IVY backend."""

    base_url: str = "http://127.0.0.1:8000"
    username: str = "admin"
    password_plaintext: str | None = None
    password_encrypted: bytes | None = None
    verify_ssl: bool = True


@dataclass(slots=True)
class AudioSettings:
    """Audio capture and playback settings."""

    input_device: str | None = None
    output_device: str | None = None
    asr_model: str = "faster-whisper-tiny"
    asr_fast_model: str = "faster-whisper-small"
    tts_voice: str = "fr-FR-piper-high/fr/fr_FR/upmc/medium"
    tts_length_scale: float = 0.92
    tts_pitch: float = 0.85
    enable_gpu: bool = True
    eco_mode: bool = True
    vad_aggressiveness: int = 2
    auto_optimize_tts: bool = True


@dataclass(slots=True)
class ProfileSettings:
    """User-specific tuning collected over time."""

    concise_mode: bool = True
    favorite_topics: dict[str, int] = field(default_factory=dict)
    last_suggestion_topic: str | None = None


@dataclass(slots=True)
class ShortcutSettings:
    """Keyboard shortcuts for the client."""

    push_to_talk: str = "Ctrl+Alt+E"
    pause_tts: str = "Ctrl+Alt+P"
    stop_tts: str = "Ctrl+Alt+S"


@dataclass(slots=True)
class CacheSettings:
    """Control of the local response cache."""

    max_entries: int = 20
    ttl_seconds: int = 86_400


@dataclass(slots=True)
class IndicatorSettings:
    """Color mapping for the server status icons."""

    ok: Color = "green"
    reconnecting: Color = "orange"
    error: Color = "red"


@dataclass(slots=True)
class AppSettings:
    """Full set of settings for the voice client."""

    server: ServerSettings = field(default_factory=ServerSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    shortcuts: ShortcutSettings = field(default_factory=ShortcutSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    indicators: IndicatorSettings = field(default_factory=IndicatorSettings)
    profile: ProfileSettings = field(default_factory=ProfileSettings)
