from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
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
    sid = uuid4().hex
    session = Session(id=sid, client=client, start_ts=_now_iso(), last_activity=_now_iso(), active=True)
    _SESSIONS[sid] = session
    return session


def get(session_id: str) -> Optional[Session]:
    return _SESSIONS.get(session_id)


def is_active(session_id: str) -> bool:
    session = _SESSIONS.get(session_id)
    return bool(session and session.active)


def list_active() -> List[dict]:
    return [s.__dict__ for s in _SESSIONS.values() if s.active]


def terminate(session_id: str) -> bool:
    session = _SESSIONS.get(session_id)
    if not session:
        return False
    session.active = False
    session.last_activity = _now_iso()
    return True


def drop(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


def touch(session_id: str) -> None:
    session = _SESSIONS.get(session_id)
    if session and session.active:
        session.last_activity = _now_iso()
