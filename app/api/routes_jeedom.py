from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import Settings
from app.core.security import require_jwt_or_api_key

router = APIRouter(prefix="/jeedom", tags=["jeedom"])


@router.get("/status")
async def jeedom_status(_: None = Depends(require_jwt_or_api_key)) -> dict:
    settings = Settings()
    return {
        "configured": bool(settings.jeedom_base_url and settings.jeedom_api_key),
        "base_url": settings.jeedom_base_url,
    }
