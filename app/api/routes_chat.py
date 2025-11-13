from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import chat_store
from app.core.chat_engine import process_question


router = APIRouter(prefix="/chat", tags=["chat"])


class ChatQuery(BaseModel):
    question: str = Field(..., min_length=1)
    conversation_id: Optional[int] = Field(default=None)
    user: Optional[str] = Field(default=None)


class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationRename(BaseModel):
    title: Optional[str] = None


@router.post("/query")
async def chat_query(payload: ChatQuery, request: Request) -> dict[str, Any]:
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="question vide")
    try:
        result = await process_question(
            payload.question.strip(),
            conversation_id=payload.conversation_id,
            user=payload.user or getattr(request.state, "user", {}).get("sub"),
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
    }


@router.get("/conversations")
async def list_conversations(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    items = await chat_store.list_conversations(limit=limit, offset=offset)
    total = await chat_store.count_conversations()
    return {"items": items, "total": total}


@router.post("/conversations")
async def create_conversation(payload: ConversationCreate) -> dict[str, Any]:
    conv = await chat_store.create_conversation(payload.title)
    return conv


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: int, payload: ConversationRename) -> dict[str, Any]:
    conv = await chat_store.rename_conversation(conversation_id, payload.title)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation introuvable")
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int) -> dict[str, Any]:
    await chat_store.delete_conversation(conversation_id)
    return {"status": "deleted"}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: int, limit: int = 100, before_id: Optional[int] = None) -> dict[str, Any]:
    messages = await chat_store.list_messages(conversation_id, limit=limit, before_id=before_id)
    return {"items": messages}





