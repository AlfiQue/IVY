from __future__ import annotations

import time
from typing import Tuple

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.security import (
    _load_admin_hash,
    create_jwt,
    generate_csrf_token,
    verify_password,
)
from app.core.config import get_settings
from app.core.sessions import create_session
from app.core.errors import error_response

router = APIRouter(prefix="/auth", tags=["auth"])


ATTEMPTS: dict[Tuple[str, str], Tuple[int, float]] = {}
MAX_ATTEMPTS = 5
COOLDOWN_S = [600, 1800, 3600]  # 10min, 30min, 60min


def _register_failure(user: str, ip: str) -> float:
    now = time.time()
    count, until = ATTEMPTS.get((user, ip), (0, 0.0))
    count += 1
    delay = COOLDOWN_S[min(max(0, count - MAX_ATTEMPTS), len(COOLDOWN_S) - 1)] if count > MAX_ATTEMPTS else 0
    until = now + delay if delay else 0.0
    ATTEMPTS[(user, ip)] = (count, until)
    return until


def _is_locked(user: str, ip: str) -> float:
    now = time.time()
    count, until = ATTEMPTS.get((user, ip), (0, 0.0))
    if until and now < until:
        return until - now
    return 0.0


@router.post("/login")
async def login(data: dict, request: Request, response: Response) -> dict:
    """Authentification admin avec bcrypt + JWT et CSRF."""
    user = data.get("user")
    password = data.get("password")
    client_ip = request.client.host if request.client else "?"
    if _is_locked(user or "?", client_ip) > 0:
        raise HTTPException(status_code=429, detail=error_response("IVY_0001", "Too many attempts. Try later."))
    if user != "admin" or not isinstance(password, str):
        until = _register_failure(user or "?", client_ip)
        raise HTTPException(status_code=401, detail=error_response("IVY_0002", "invalid credentials", details={"retry_after_sec": int(until - time.time()) if until else 0}))

    hashed = _load_admin_hash()
    if not hashed or not verify_password(password, hashed):
        raise HTTPException(status_code=401, detail=error_response("IVY_0002", "invalid credentials"))

    token = create_jwt("admin")
    # Cookie HttpOnly pour le JWT
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    # CSRF renvoyé à l'UI, à présenter via X-CSRF-Token côté client
    settings = get_settings()
    sess = create_session("webui")
    csrf = generate_csrf_token(settings.jwt_secret, sess.id)
    response.set_cookie("session_id", sess.id, httponly=False)
    return {"csrf_token": csrf, "session_id": sess.id}


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie("access_token")
    return {"status": "ok"}
