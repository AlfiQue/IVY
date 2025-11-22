"""Data schemas exchanged with the IVY backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Optional


class CommandRisk(str, Enum):
    """Local command risk level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CommandType(str, Enum):
    """Type of command to execute locally."""

    APP_LAUNCH = "app_launch"
    SCRIPT = "script"
    KEYSTROKE = "keystroke"
    CUSTOM = "custom"


@dataclass(slots=True)
class SystemCommand:
    """Description of a command to execute on the local machine."""

    type: CommandType
    id: str
    display_name: str
    action: str
    args: list[str] = field(default_factory=list)
    require_confirm: bool = False
    fallback_hint: str | None = None
    source: Literal["memory", "llm", "user"] = "llm"
    risk_level: CommandRisk = CommandRisk.LOW

    def to_payload(self) -> dict[str, Any]:
        """Serialize the command for API calls."""
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, CommandType) else str(self.type),
            "display_name": self.display_name,
            "action": self.action,
            "args": list(self.args or []),
            "require_confirm": self.require_confirm,
            "fallback_hint": self.fallback_hint,
            "source": self.source,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, CommandRisk) else str(self.risk_level),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SystemCommand":
        """Construct a SystemCommand from metadata payload."""
        raw_type = payload.get("type") or CommandType.CUSTOM
        try:
            cmd_type = CommandType(raw_type)
        except ValueError:
            cmd_type = CommandType.CUSTOM
        raw_risk = payload.get("risk_level") or CommandRisk.LOW
        try:
            risk = CommandRisk(raw_risk)
        except ValueError:
            risk = CommandRisk.LOW
        return cls(
            type=cmd_type,
            id=str(payload.get("id") or payload.get("action") or "cmd-unknown"),
            display_name=payload.get("display_name") or payload.get("id"),
            action=payload.get("action") or "",
            args=list(payload.get("args") or []),
            require_confirm=bool(payload.get("require_confirm", False)),
            fallback_hint=payload.get("fallback_hint"),
            source=payload.get("source") or "llm",
            risk_level=risk,
        )


@dataclass(slots=True)
class VoiceStreamChunk:
    """Single frame of audio streamed to the backend."""

    frame: bytes
    sample_rate: int
    timestamp: float


@dataclass(slots=True)
class TranscriptEvent:
    """Transcription event produced while streaming voice."""

    text: str
    final: bool = False
    confidence: Optional[float] = None


@dataclass(slots=True)
class ChatMessage:
    """Conversation message."""

    role: Literal["user", "assistant", "system"]
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
