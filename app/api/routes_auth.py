from __future__ import annotations

import time
from typing import Tuple
import logging

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.security import (
    JWT_EXPIRE_HOURS,
    _load_admin_hash,
    create_jwt,
    generate_csrf_token,
    verify_password,
)
from app.core.config import get_settings
from app.core import sessions
from app.core.errors import error_response

logger = logging.getLogger("auth")

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


def _cookie_flags():
    settings = get_settings()
    same_site = str(getattr(settings, "cookie_samesite", "lax") or "lax").lower()
    if same_site not in {"lax", "strict", "none"}:
        same_site = "lax"
    secure = bool(getattr(settings, "cookie_secure", False))
    if same_site == "none":
        secure = True
    return secure, same_site, settings



@router.post("/login")
async def login(data: dict, request: Request, response: Response) -> dict:
    """Authentification admin avec bcrypt + JWT et CSRF."""
    try:
        user = data.get("user")
        password = data.get("password")
        client_ip = request.client.host if request.client else "?"
        if _is_locked(user or "?", client_ip) > 0:
            raise HTTPException(status_code=429, detail=error_response("IVY_0001", "Too many attempts. Try later."))
        if user != "admin" or not isinstance(password, str):
            until = _register_failure(user or "?", client_ip)
            raise HTTPException(
                status_code=401,
                detail=error_response(
                    "IVY_0002",
                    "invalid credentials",
                    details={"retry_after_sec": int(until - time.time()) if until else 0},
                ),
            )

        hashed = _load_admin_hash()
        if not hashed or not verify_password(password, hashed):
            raise HTTPException(status_code=401, detail=error_response("IVY_0002", "invalid credentials"))

        ATTEMPTS.pop(((user or "?"), client_ip), None)

        secure_cookie, same_site, settings = _cookie_flags()
        if settings.jwt_secret == "CHANGE_ME" or len(settings.jwt_secret) < 16:
            raise HTTPException(
                status_code=500,
                detail=error_response(
                    "IVY_5001",
                    "jwt_secret non configure",
                    details={"hint": "Definir JWT_SECRET dans l'environnement ou config.json"},
                ),
            )

        token = create_jwt("admin")
        access_max_age = JWT_EXPIRE_HOURS * 3600
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            samesite=same_site,
            secure=secure_cookie,
            max_age=access_max_age,
        )

        session = sessions.create_session("webui")
        csrf = generate_csrf_token(settings.jwt_secret, session.id)
        session_max_age = max(int(getattr(settings, "csrf_max_age_seconds", 3600)), 60)
        response.set_cookie(
            key="session_id",
            value=session.id,
            httponly=True,
            secure=secure_cookie,
            samesite=same_site,
            max_age=session_max_age,
        )
        return {"csrf_token": csrf, "session_id": session.id}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - observability for unexpected failures
        logger.exception("Login failed", exc_info=exc)
        raise
@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    sid = request.cookies.get("session_id") if request.cookies else None
    if sid:
        sessions.terminate(sid)
        sessions.drop(sid)
        response.delete_cookie("session_id")
    response.delete_cookie("access_token")
    return {"status": "ok"}




