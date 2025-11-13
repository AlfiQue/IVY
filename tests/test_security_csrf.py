from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import sessions
from app.core.config import get_settings
from app.core.security import csrf_protect, generate_csrf_token


app = FastAPI()


@app.post("/protected")
async def _protected(_: None = Depends(csrf_protect)) -> dict[str, bool]:
    return {"ok": True}


def _configure_secret() -> str:
    settings = get_settings()
    if settings.jwt_secret == "CHANGE_ME":
        raise RuntimeError("JWT secret not patched for tests")
    return settings.jwt_secret


def test_csrf_protect_accepts_valid_session(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "tests-secret-value-123456789")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    secret = _configure_secret()
    session = sessions.create_session("tests")
    token = generate_csrf_token(secret, session.id)
    with TestClient(app) as client:
        client.cookies.set("session_id", session.id)
        resp = client.post("/protected", headers={"X-CSRF-Token": token})
        assert resp.status_code == 200
    sessions.drop(session.id)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_csrf_protect_rejects_missing_session(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "tests-secret-value-987654321")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    secret = _configure_secret()
    session = sessions.create_session("tests")
    token = generate_csrf_token(secret, session.id)
    sessions.terminate(session.id)
    sessions.drop(session.id)
    with TestClient(app) as client:
        client.cookies.set("session_id", session.id)
        resp = client.post("/protected", headers={"X-CSRF-Token": token})
        assert resp.status_code == 403
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()  # type: ignore[attr-defined]

