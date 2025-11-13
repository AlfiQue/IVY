from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Request

from app.core.rag import RAGEngine
from app.core.config import get_settings

from app.core.security import require_jwt_or_api_key


async def _rag_auth(request: Request):
    return await require_jwt_or_api_key(request, scopes=["rag"])


router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/reindex")
async def reindex(payload: dict | None = None, _: None = Depends(_rag_auth)) -> dict[str, int]:
    """Force l'indexation RAG (complète par défaut)."""
    settings = get_settings()
    engine = RAGEngine(settings)
    force = bool((payload or {}).get("full", True))
    count = engine.reindex(full=force)
    return {"indexed": count}


@router.post("/query")
async def query(payload: dict, _: None = Depends(_rag_auth)) -> dict:
    text = payload.get("query")
    top_k = int(payload.get("top_k", 5))
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="Champ 'query' invalide")
    settings = get_settings()
    engine = RAGEngine(settings)
    results = engine.query(text, top_k=top_k)
    return {"results": results}
