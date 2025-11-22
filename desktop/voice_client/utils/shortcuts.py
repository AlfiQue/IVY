"""Global shortcut helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class Shortcut:
    """Keyboard shortcut descriptor."""

    name: str
    sequence: str


def validate_shortcut(sequence: str, existing: Iterable[str]) -> bool:
    """Return True when the shortcut does not conflict with existing ones."""
    normalized = sequence.strip().lower()
    return normalized not in (s.strip().lower() for s in existing)
