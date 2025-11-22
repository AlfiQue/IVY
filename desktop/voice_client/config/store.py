"""Persistence helpers for IVY voice client settings."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from pathlib import Path

from .paths import config_dir, project_root
from .settings import AppSettings, AudioSettings, CacheSettings, IndicatorSettings, ServerSettings, ShortcutSettings


def _settings_path() -> Path:
    """Primary path for persisted settings."""
    return config_dir() / "voice_settings.json"


def _legacy_path() -> Path:
    """Older path (historic bug placing file under desktop/desktop/...)."""
    return project_root() / "desktop" / "desktop" / "voice_client" / "config" / "voice_settings.json"


def load_settings() -> AppSettings:
    """Load settings from disk (defaults when missing)."""
    path = _settings_path()
    legacy = _legacy_path()

    if not path.exists() and legacy.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        legacy.replace(path)

    if not path.exists():
        return AppSettings()

    raw_text = path.read_text(encoding="utf-8").lstrip("\ufeff")
    data = json.loads(raw_text)

    server_payload = data.get("server", {})
    encoded = server_payload.get("password_encrypted")
    if encoded:
        try:
            server_payload["password_encrypted"] = base64.b64decode(encoded)
        except (ValueError, TypeError):
            server_payload["password_encrypted"] = None
    else:
        server_payload["password_encrypted"] = None
    server_payload.setdefault("password_plaintext", None)

    return AppSettings(
        server=ServerSettings(**server_payload),
        audio=AudioSettings(**data.get("audio", {})),
        shortcuts=ShortcutSettings(**data.get("shortcuts", {})),
        cache=CacheSettings(**data.get("cache", {})),
        indicators=IndicatorSettings(**data.get("indicators", {})),
    )


def save_settings(settings: AppSettings) -> None:
    """Persist settings to disk (password encrypted in base64 if present)."""
    payload = asdict(settings)
    server = payload.get("server", {})
    encrypted = server.get("password_encrypted")
    if encrypted:
        server["password_encrypted"] = base64.b64encode(encrypted).decode("ascii")
    else:
        server["password_encrypted"] = None

    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
