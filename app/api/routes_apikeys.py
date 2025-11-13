from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_jwt, csrf_protect
from app.core import apikeys


router = APIRouter(prefix="/apikeys", tags=["apikeys"])


@router.get("")
async def list_apikeys(_: None = Depends(require_jwt)) -> dict:
    return {"keys": apikeys.list_keys()}


@router.post("")
async def create_apikey(payload: dict, _: None = Depends(require_jwt), __: None = Depends(csrf_protect)) -> dict:
    name = payload.get("name") or "default"
    scopes = payload.get("scopes") or []
    if not isinstance(scopes, list):
        raise HTTPException(status_code=400, detail={"error": {"code": "IVY_4000", "message": "invalid scopes"}})
    created = apikeys.create_key(str(name), [str(s) for s in scopes])
    return created


@router.delete("/{key_id}")
async def delete_apikey(key_id: str, _: None = Depends(require_jwt), __: None = Depends(csrf_protect)) -> dict:
    ok = apikeys.delete_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"error": {"code": "IVY_4040", "message": "not_found"}})
    return {"status": "deleted"}
