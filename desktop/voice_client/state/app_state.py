"""Shared state model for the voice client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..config.settings import AppSettings
from ..services.schemas import ChatMessage, SystemCommand


ServerStatus = Literal["online", "reconnecting", "offline"]


@dataclass(slots=True)
class ConversationEntry:
    """Single conversation entry."""

    message: ChatMessage
    source: Literal["text", "voice", "command"]


@dataclass(slots=True)
class AppState:
    """Global state for the client."""

    settings: AppSettings = field(default_factory=AppSettings)
    server_status: ServerStatus = "offline"
    history: list[ConversationEntry] = field(default_factory=list)
    pending_command: SystemCommand | None = None
    listening: bool = False
    speaking: bool = False
