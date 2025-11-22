from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core import chat_store
from app.core.classifier import classify_with_heuristic, classify_with_llm
from app.core.embeddings import embed_text
from app.core.security import require_jwt_or_api_key


router = APIRouter(prefix="/memory", tags=["memory"])


async def _memory_auth(request: Request):
    return await require_jwt_or_api_key(request, scopes=["memory"])


def _sanitize_qa(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(item)
    cleaned.pop("embedding", None)
    cleaned.pop("embedding_dim", None)
    return cleaned


class QAUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    is_variable: Optional[bool] = None
    origin: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class QAImport(BaseModel):
    items: list[dict[str, Any]]


@router.get("/qa", dependencies=[Depends(_memory_auth)])
async def list_qa(limit: int = 50, offset: int = 0, search: Optional[str] = None) -> dict[str, Any]:
    data = await chat_store.list_qa(limit=limit, offset=offset, search=search)
    return data


@router.patch("/qa/{qa_id}", dependencies=[Depends(_memory_auth)])
async def update_qa(qa_id: int, payload: QAUpdate) -> dict[str, Any]:
    existing = await chat_store.get_qa(qa_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="QA introuvable")
    fields: dict[str, Any] = {}
    if payload.question is not None:
        fields["question"] = payload.question
        try:
            fields["embedding"] = await embed_text(payload.question)
        except Exception:
            fields["embedding"] = None
    if payload.answer is not None:
        fields["answer"] = payload.answer
    if payload.is_variable is not None:
        fields["is_variable"] = payload.is_variable
    if payload.origin is not None:
        fields["origin"] = payload.origin
    if payload.metadata is not None:
        fields["metadata"] = payload.metadata
    updated = await chat_store.update_qa(qa_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="QA introuvable")
    return _sanitize_qa(updated)


@router.delete("/qa/{qa_id}", dependencies=[Depends(_memory_auth)])
async def delete_qa(qa_id: int) -> dict[str, Any]:
    await chat_store.delete_qa(qa_id)
    return {"status": "deleted"}


@router.post("/qa/{qa_id}/classify/llm", dependencies=[Depends(_memory_auth)])
async def qa_classify_llm(qa_id: int, update_flag: bool = False) -> dict[str, Any]:
    item = await chat_store.get_qa(qa_id)
    if item is None:
        raise HTTPException(status_code=404, detail="QA introuvable")
    result = await classify_with_llm(item["question"])
    updated = None
    if update_flag:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        meta["classification_llm"] = result
        refresh = result.get("refresh_interval_days")
        if isinstance(refresh, (int, float)) and refresh >= 0:
            meta["refresh_interval_days"] = int(refresh)
            meta["last_refreshed_at"] = datetime.now(timezone.utc).isoformat()
        updated = await chat_store.update_qa(qa_id, is_variable=result.get("is_variable"), metadata=meta)
    payload = {"classification": result}
    if updated is not None:
        payload["qa"] = _sanitize_qa(updated)
    return payload


@router.post("/qa/{qa_id}/classify/heuristic", dependencies=[Depends(_memory_auth)])
async def qa_classify_heuristic(qa_id: int, update_flag: bool = False) -> dict[str, Any]:
    item = await chat_store.get_qa(qa_id)
    if item is None:
        raise HTTPException(status_code=404, detail="QA introuvable")
    result = classify_with_heuristic(item["question"])
    updated = None
    if update_flag:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        meta["classification_heuristic"] = result
        refresh = result.get("refresh_interval_days")
        if isinstance(refresh, (int, float)) and refresh >= 0:
            meta["refresh_interval_days"] = int(refresh)
            meta["last_refreshed_at"] = datetime.now(timezone.utc).isoformat()
        updated = await chat_store.update_qa(qa_id, is_variable=result.get("is_variable"), metadata=meta)
    payload = {"classification": result}
    if updated is not None:
        payload["qa"] = _sanitize_qa(updated)
    return payload


@router.post("/qa/import", dependencies=[Depends(_memory_auth)])
async def import_qa(payload: QAImport) -> dict[str, Any]:
    outcome = await chat_store.import_qa(payload.items)
    return outcome


@router.get("/qa/export", dependencies=[Depends(_memory_auth)])
async def export_qa() -> dict[str, Any]:
    items = await chat_store.export_qa()
    sanitized = [_sanitize_qa(item) for item in items]
    return {"items": sanitized}
from datetime import datetime, timezone
