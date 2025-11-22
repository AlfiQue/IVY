"""Filesystem helpers for the voice client."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parents[3]


def voice_client_root() -> Path:
    """Return the root folder of the voice client."""
    return project_root() / "desktop" / "voice_client"


def config_dir() -> Path:
    """Directory storing local configuration and credentials."""
    root = voice_client_root() / "config"
    root.mkdir(parents=True, exist_ok=True)
    return root


def models_dir() -> Path:
    """Directory storing audio models."""
    root = voice_client_root() / "resources" / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root
