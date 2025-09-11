from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.core.errors import error_response

from app.core import sessions

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
def list_sessions() -> dict:
    return {"sessions": sessions.list_active()}


@router.post("/{session_id}/terminate")
def terminate_session(session_id: str) -> dict:
    ok = sessions.terminate(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail=error_response("IVY_4042", "session not found"))
    return {"status": "terminated"}
