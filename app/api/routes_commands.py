from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import require_jwt_or_api_key

COMMAND_LOG_PATH = Path("app/logs/commands.jsonl")
COMMAND_REPORT_PATH = Path("app/logs/commands_learning.jsonl")

router = APIRouter(prefix="/commands", tags=["commands"])


class CommandData(BaseModel):
    id: str
    type: str | None = None
    display_name: str | None = None
    action: str | None = None
    args: list[str] = Field(default_factory=list)
    require_confirm: bool = False
    risk_level: str | None = None
    source: str | None = None


class CommandAckPayload(CommandData):
    status: Literal["accepted", "ignored", "rejected"] = "accepted"
    note: str | None = None


class CommandReportPayload(BaseModel):
    command: CommandData
    note: str | None = None


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


@router.post("/ack")
async def acknowledge_command(
    payload: CommandAckPayload,
    _: None = Depends(require_jwt_or_api_key),
) -> dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": payload.status,
        "note": payload.note,
        "command": payload.model_dump(exclude={"status", "note"}),
    }
    _append_jsonl(COMMAND_LOG_PATH, entry)
    return {"status": "ok"}


@router.post("/report")
async def report_command(
    payload: CommandReportPayload,
    _: None = Depends(require_jwt_or_api_key),
) -> dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "command": payload.command.model_dump(),
        "note": payload.note,
    }
    _append_jsonl(COMMAND_REPORT_PATH, entry)
    return {"status": "ok"}
