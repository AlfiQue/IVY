from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.security import csrf_protect, require_jwt


router = APIRouter(prefix="/config", tags=["config"])

_SENSITIVE_KEYS = {"jwt_secret"}


def _config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config.json"


def _load_current(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _sanitize_config(data: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key, value in data.items():
        if key in _SENSITIVE_KEYS:
            sanitized[key] = "***"
        else:
            sanitized[key] = value
    return sanitized


@router.get("")
async def get_config(_: None = Depends(require_jwt)) -> Dict[str, Any]:
    settings = get_settings()
    return _sanitize_config(settings.model_dump())


@router.put("")
async def update_config(payload: Dict[str, Any], _: None = Depends(require_jwt), __: None = Depends(csrf_protect)) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"error": {"code": "IVY_4000", "message": "invalid payload"}})

    path = _config_path()
    current = _load_current(path)
    merged = {**current, **payload}

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)

    get_settings.cache_clear()  # type: ignore[attr-defined]
    updated = get_settings()
    return _sanitize_config(updated.model_dump())
