from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.rag import RAGEngine
from app.core.config import get_settings

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/reindex")
async def reindex(payload: dict | None = None) -> dict[str, int]:
    """Force l'indexation RAG (complète par défaut)."""
    settings = get_settings()
    engine = RAGEngine(settings)
    force = bool((payload or {}).get("full", True))
    count = engine.reindex(full=force)
    return {"indexed": count}


@router.post("/query")
async def query(payload: dict) -> dict:
    text = payload.get("query")
    top_k = int(payload.get("top_k", 5))
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="Champ 'query' invalide")
    settings = get_settings()
    engine = RAGEngine(settings)
    results = engine.query(text, top_k=top_k)
    return {"results": results}
