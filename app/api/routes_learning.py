from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core import learning
from app.core.security import require_jwt_or_api_key

router = APIRouter(prefix="/learning", tags=["learning"])


class FeedbackPayload(BaseModel):
    qa_id: int | None = Field(default=None)
    question: str
    answer: str
    helpful: bool
    origin: str | None = Field(default="voice")
    comment: str | None = Field(default=None)


@router.get("/insights")
async def get_learning_insights(limit: int = 10, _: None = Depends(require_jwt_or_api_key)) -> dict:
    limit = max(1, min(limit, 25))
    return await learning.build_learning_summary(limit_prompts=limit, limit_jobs=min(limit, 10), query_limit=limit)


@router.post("/feedback")
async def submit_learning_feedback(payload: FeedbackPayload, _: None = Depends(require_jwt_or_api_key)) -> dict:
    await learning.record_feedback(
        question=payload.question,
        answer=payload.answer,
        helpful=payload.helpful,
        qa_id=payload.qa_id,
        origin=payload.origin,
        note=payload.comment,
    )
    return {"status": "recorded"}
