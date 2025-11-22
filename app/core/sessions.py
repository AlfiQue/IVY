from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List
from uuid import uuid4


@dataclass
class Session:
    id: str
    client: str
    start_ts: str
    last_activity: str
    active: bool = True


_SESSIONS: Dict[str, Session] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(client: str) -> Session:
    sid = uuid4().hex[:12]
    s = Session(id=sid, client=client, start_ts=_now_iso(), last_activity=_now_iso(), active=True)
    _SESSIONS[sid] = s
    return s


def list_active() -> List[dict]:
    return [s.__dict__ for s in _SESSIONS.values() if s.active]


def is_active(session_id: str) -> bool:
    s = _SESSIONS.get(session_id)
    return bool(s and s.active)


def terminate(session_id: str) -> bool:
    s = _SESSIONS.get(session_id)
    if not s:
        return False
    s.active = False
    s.last_activity = _now_iso()
    return True


def touch(session_id: str) -> None:
    s = _SESSIONS.get(session_id)
    if s and s.active:
        s.last_activity = _now_iso()

