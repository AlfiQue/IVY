from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.metrics import inc_auth_error


audit_logger = logging.getLogger("audit")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 12


# ----- Password utils -----
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def regenerate_password(password: str, source: str) -> str:
    hashed = hash_password(password)
    audit_logger.info(
        "Mot de passe rǸgǸnǸrǸ",
        extra={"timestamp": datetime.utcnow().isoformat(), "source": source},
    )
    return hashed


# ----- JWT utils -----
def create_jwt(subject: str, *, hours: int = JWT_EXPIRE_HOURS) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(hours=hours)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return {}


# RÃ©tro-compat interne
def create_token(subject: str, expires_delta: timedelta | None = None) -> str:  # pragma: no cover
    hours = JWT_EXPIRE_HOURS if expires_delta is None else int(expires_delta.total_seconds() // 3600)
    return create_jwt(subject, hours=hours)


def verify_token(token: str) -> dict[str, Any]:  # pragma: no cover
    return verify_jwt(token)


# ----- CSRF utils + dependency -----
def generate_csrf_token(secret_key: str, user_id: str) -> str:
    serializer = URLSafeTimedSerializer(secret_key)
    return serializer.dumps(user_id)


def validate_csrf_token(secret_key: str, token: str, max_age: int = 3600) -> bool:
    serializer = URLSafeTimedSerializer(secret_key)
    try:
        serializer.loads(token, max_age=max_age)
        return True
    except (BadSignature, SignatureExpired):
        return False


async def csrf_protect(csrf: str | None = Header(default=None, alias="X-CSRF-Token")) -> None:
    settings = get_settings()
    if not csrf or not validate_csrf_token(settings.jwt_secret, csrf):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF invalide")


async def require_jwt(request: Request) -> None:
    """Dépendance FastAPI: exige un cookie JWT valide (admin)."""
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
        "Reset admin demand",
        extra={"timestamp": datetime.utcnow().isoformat(), "action": "reset_admin"},
    )
    print(f"[RESET-ADMIN] Nouveau Mot de passe rǸgǸnǸrǸre: {temp_password}")
    return temp_password


# ----- Middleware -----
def attach_user_middleware():
    async def middleware(request: Request, call_next):
        token = request.cookies.get("access_token")
        if token:
            payload = verify_jwt(token)
            sub = payload.get("sub") if isinstance(payload, dict) else None
            if sub:
                request.state.user = {"sub": sub}
        return await call_next(request)

    return middleware




