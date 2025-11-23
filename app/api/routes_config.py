from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.restart import restart_and_exit
from app.core.security import csrf_protect, require_jwt


router = APIRouter(prefix="/config", tags=["config"])

_SENSITIVE_KEYS = {"jwt_secret", "jeedom_api_key"}
_MAX_IMPORT_BYTES = 512 * 1024  # 512 ko


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


def _validate_payload(candidate: Dict[str, Any]) -> None:
    try:
        Settings.model_validate(candidate)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "IVY_4007",
                    "message": "configuration invalide",
                    "details": exc.errors(),
                }
            },
        ) from exc


def _write_config(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        with path.open("w", encoding="utf-8") as stream:
            stream.write(content)
    except PermissionError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "IVY_5001",
                    "message": "Impossible d'écrire config.json : vérifiez les droits ou les processus en cours.",
                }
            },
        ) from exc


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

    _validate_payload(merged)
    _write_config(path, merged)

    get_settings.cache_clear()  # type: ignore[attr-defined]
    updated = get_settings()
    return _sanitize_config(updated.model_dump())


@router.post("/import")
async def import_config(
    file: UploadFile = File(...),
    _: None = Depends(require_jwt),
    __: None = Depends(csrf_protect),
) -> Dict[str, Any]:
    try:
        raw = await file.read()
    finally:
        try:
            await file.close()
        except Exception:  # pragma: no cover - best effort
            pass
    if not raw:
        raise HTTPException(status_code=400, detail={"error": {"code": "IVY_4002", "message": "fichier vide"}})
    if len(raw) > _MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "IVY_4003", "message": "fichier trop volumineux (limite 512 ko)"}},
        )
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "IVY_4004", "message": "encodage invalide"}}) from exc
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "IVY_4005", "message": "JSON invalide"}}) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"error": {"code": "IVY_4006", "message": "le fichier doit contenir un objet JSON"}})

    _validate_payload(payload)
    path = _config_path()
    _write_config(path, payload)

    get_settings.cache_clear()  # type: ignore[attr-defined]
    updated = get_settings()
    return {
        "status": "imported",
        "config": _sanitize_config(updated.model_dump()),
    }


@router.post("/restart")
async def restart_server(
    background: BackgroundTasks,
    _: None = Depends(require_jwt),
    __: None = Depends(csrf_protect),
) -> Dict[str, Any]:
    background.add_task(restart_and_exit)
    return {"status": "restarting"}
