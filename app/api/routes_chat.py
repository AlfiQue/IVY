from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError

from app.core import chat_store
from app.core.chat_engine import process_question
from app.core.security import require_jwt_or_api_key


router = APIRouter(prefix="/chat", tags=["chat"])


async def _chat_auth(request: Request):
    return await require_jwt_or_api_key(request)


class ChatQuery(BaseModel):
    question: str = Field(..., min_length=1)
    conversation_id: Optional[int] = Field(default=None)
    user: Optional[str] = Field(default=None)
    response_mode: Optional[str] = Field(default=None)
    use_speculative: Optional[bool] = Field(default=None, alias="use_speculative")


class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationRename(BaseModel):
    title: Optional[str] = None


@router.post("/query", dependencies=[Depends(_chat_auth)])
async def chat_query(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    raw: dict[str, Any]
    if isinstance(body, dict) and isinstance(body.get("payload"), dict):
        raw = body["payload"]
    elif isinstance(body, dict):
        raw = body
    else:
        raise HTTPException(status_code=422, detail="payload invalide")
    try:
        payload = ChatQuery.model_validate(raw)  # type: ignore[attr-defined]
    except AttributeError:
        try:
            payload = ChatQuery(**raw)
        except ValidationError as exc:  # pragma: no cover
            raise HTTPException(status_code=422, detail=jsonable_encoder(exc.errors())) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=jsonable_encoder(exc.errors())) from exc
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="question vide")
    try:
        result = await process_question(
            payload.question.strip(),
            conversation_id=payload.conversation_id,
            user=payload.user or getattr(request.state, "user", {}).get("sub"),
             response_mode=payload.response_mode,
            speculative_override=payload.use_speculative,
        )
    except RuntimeError as exc:
        detail = {
            "error": {
                "code": "IVY_LLM_503",
                "message": "LLM indisponible : configurez `llm_model_path` ou TensorRT-LLM",
                "details": str(exc),
            }
        }
        raise HTTPException(status_code=503, detail=detail) from exc
    answer_message = result["answer_message"]
    return {
        "conversation_id": result["conversation_id"],
        "origin": result["origin"],
        "answer": answer_message["content"],
        "answer_message": answer_message,
        "question_message": result["question_message"],
        "qa_id": result.get("qa_id"),
        "classification": result.get("classification"),
        "search_results": result.get("search_results", []),
        "is_variable": result.get("is_variable", False),
        "latency_ms": result.get("latency_ms"),
        "speculative": result.get("speculative", False),
        "match": result.get("match"),
    }


@router.get("/conversations", dependencies=[Depends(_chat_auth)])
async def list_conversations(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    items = await chat_store.list_conversations(limit=limit, offset=offset)
    total = await chat_store.count_conversations()
    return {"items": items, "total": total}


@router.post("/conversations", dependencies=[Depends(_chat_auth)])
async def create_conversation(payload: ConversationCreate) -> dict[str, Any]:
    conv = await chat_store.create_conversation(payload.title)
    return conv


@router.patch("/conversations/{conversation_id}", dependencies=[Depends(_chat_auth)])
async def rename_conversation(conversation_id: int, payload: ConversationRename) -> dict[str, Any]:
    conv = await chat_store.rename_conversation(conversation_id, payload.title)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation introuvable")
    return conv


@router.delete("/conversations/{conversation_id}", dependencies=[Depends(_chat_auth)])
async def delete_conversation(conversation_id: int) -> dict[str, Any]:
    await chat_store.delete_conversation(conversation_id)
    return {"status": "deleted"}


@router.get("/conversations/{conversation_id}/messages", dependencies=[Depends(_chat_auth)])
async def list_messages(conversation_id: int, limit: int = 100, before_id: Optional[int] = None) -> dict[str, Any]:
    messages = await chat_store.list_messages(conversation_id, limit=limit, before_id=before_id)
    return {"items": messages}





