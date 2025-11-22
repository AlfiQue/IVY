from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.metrics import inc_auth_error
from app.core import apikeys, sessions as sessions_module
from app.core.logger import get_logger


audit_logger = get_logger("audit")

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

def _auth_disabled() -> bool:
    try:
        settings = get_settings()
    except Exception:
        return False
    return bool(getattr(settings, 'disable_auth', False))

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 12


# ----- Password utils -----
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    if hashed_password.startswith(("$2b$", "$2a$", "$2y$")):
        try:
            import bcrypt  # type: ignore

            return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False
    return pwd_context.verify(password, hashed_password)


def regenerate_password(password: str, source: str) -> str:
    hashed = hash_password(password)
    audit_logger.info(
        "Mot de passe régénéré",
        extra={"timestamp": datetime.now(timezone.utc).isoformat(), "source": source},
    )
    return hashed


# ----- JWT utils -----
def create_jwt(subject: str, *, hours: int = JWT_EXPIRE_HOURS) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=hours)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return {}


# ----- CSRF utils + dependency -----
def generate_csrf_token(secret_key: str, user_id: str) -> str:
    serializer = URLSafeTimedSerializer(secret_key)
    return serializer.dumps(user_id)


def validate_csrf_token(secret_key: str, token: str, max_age: int = 3600) -> str | None:
    serializer = URLSafeTimedSerializer(secret_key)
    try:
        return serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


async def csrf_protect(request: Request, csrf: str | None = Header(default=None, alias="X-CSRF-Token")) -> None:
    settings = get_settings()
    cookie_sid = request.cookies.get("session_id") if request.cookies else None
    if not cookie_sid:
        # Aucun cookie de session: accès via API key ou appel hors session -> pas de vérification CSRF.
        return
    if not csrf:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF invalide")
    max_age = getattr(settings, "csrf_max_age_seconds", 3600)
    session_id = validate_csrf_token(settings.jwt_secret, csrf, max_age=max_age)
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF invalide")
    if cookie_sid != session_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF invalide")
    if not sessions_module.is_active(cookie_sid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF invalide")
    try:
        sessions_module.touch(cookie_sid)
    except Exception:
        pass

async def require_jwt(request: Request) -> None:
    """Dependance FastAPI: exige un cookie JWT valide (admin)."""
    if _auth_disabled():
        request.state.user = getattr(request.state, 'user', {"sub": "debug"})
        return None
    token = request.cookies.get("access_token") if request.cookies else None
    if not token:
        try:
            inc_auth_error()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "IVY_4010", "message": "unauthorized"}})
    payload = verify_jwt(token)
    if not isinstance(payload, dict) or not payload.get("sub"):
        try:
            inc_auth_error()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "IVY_4010", "message": "unauthorized"}})

async def require_jwt_or_api_key(request: Request, scopes: list[str] | None = None) -> None:
    """Autorise soit un cookie JWT admin, soit un header Bearer API key.

    - Header: Authorization: Bearer <API_KEY>
    - Cookie: access_token (JWT admin)
    """
    if _auth_disabled():
        request.state.user = getattr(request.state, 'user', {"sub": "debug"})
        return None
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        info = apikeys.verify_token(token, scopes)
        if info:
            request.state.user = info
            return None
    token = request.cookies.get("access_token") if request.cookies else None
    if not token:
        try:
            inc_auth_error()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "IVY_4010", "message": "unauthorized"}})
    payload = verify_jwt(token)
    if not isinstance(payload, dict) or not payload.get("sub"):
        try:
            inc_auth_error()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "IVY_4010", "message": "unauthorized"}})

# ----- Admin account management -----
def _admin_file() -> Path:
    return Path("app/data/admin.json")


def _load_admin_hash() -> str | None:
    try:
        data = json.loads(_admin_file().read_text())
        return data.get("password_hash")
    except Exception:
        return None


def _save_admin_hash(hash_value: str) -> None:
    _admin_file().parent.mkdir(parents=True, exist_ok=True)
    _admin_file().write_text(json.dumps({"password_hash": hash_value}, ensure_ascii=False))


def maybe_reset_admin() -> str | None:
    settings = get_settings()
    flag = Path(settings.reset_admin_flag)
    if not flag.exists():
        return None
    temp_password = secrets.token_urlsafe(12)
    _save_admin_hash(hash_password(temp_password))
    try:
        flag.unlink(missing_ok=True)
    finally:
        pass
    audit_logger.info(
        "Reset admin demande",
        extra={"timestamp": datetime.utcnow().isoformat(), "action": "reset_admin"},
    )
    print(f"[RESET-ADMIN] Nouveau mot de passe genere: {temp_password}")
    return temp_password


# ----- Middleware -----
def attach_user_middleware():
    async def middleware(request: Request, call_next):
        if _auth_disabled():
            request.state.user = getattr(request.state, 'user', {"sub": "debug"})
            return await call_next(request)
        token = request.cookies.get("access_token")
        if token:
            payload = verify_jwt(token)
            sub = payload.get("sub") if isinstance(payload, dict) else None
            if sub:
                request.state.user = {"sub": sub}
        return await call_next(request)

    return middleware







