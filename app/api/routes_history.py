from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import csrf_protect, require_jwt
from app.core.history import search_events

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
async def list_history(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(default=None),
    plugin: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> dict[str, Any]:
    return await search_events(limit=limit, offset=offset, q=q, plugin=plugin, start=start, end=end)


@router.post("/replay", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
async def replay() -> dict:
    return {"status": "ok"}
