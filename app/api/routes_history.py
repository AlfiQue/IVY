from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.core.security import csrf_protect, require_jwt, require_jwt_or_api_key
from app.core.history import search_events, clear_events

async def _history_auth(request: Request):
    return await require_jwt_or_api_key(request, scopes=["history"])  # read via API key


router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
async def list_history(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(default=None),
    plugin: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    type: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    _: None = Depends(_history_auth),
) -> dict[str, Any]:
    return await search_events(limit=limit, offset=offset, q=q, plugin=plugin, start=start, end=end, event_type=type, session_id=session_id)


@router.post("/replay", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
async def replay(payload: dict | None = None) -> dict:
    return {"status": "not_supported"}


@router.delete("", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
async def purge_history() -> dict:
    await clear_events()
    return {"status": "cleared"}



