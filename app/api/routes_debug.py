from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_jwt_or_api_key
from app.core.websearch import search_duckduckgo_detailed

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/search")
async def debug_search(q: str, limit: int = 5, _: None = Depends(require_jwt_or_api_key)) -> dict:
    result = await search_duckduckgo_detailed(q, max_results=limit)
    return result
