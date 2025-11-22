"""IVY voice client package."""

from __future__ import annotations

from typing import Any

__all__ = ["run"]


def run(*args: Any, **kwargs: Any) -> Any:
    """Entrypoint pour lancer le client vocal (import paresseux)."""
    from .app import run as _run

    return _run(*args, **kwargs)
