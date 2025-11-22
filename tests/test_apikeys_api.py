from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import apikeys
from app.core.security import csrf_protect, require_jwt
from app.main import app


def test_apikeys_route_crud(tmp_path, monkeypatch):
    monkeypatch.setattr(apikeys, "_FILE", tmp_path / "apikeys.json", raising=False)
    app.dependency_overrides[require_jwt] = lambda: None
    app.dependency_overrides[csrf_protect] = lambda: None
    client = TestClient(app)
    try:
        res = client.post("/apikeys", json={"name": "demo", "scopes": ["llm", "jobs"]})
        assert res.status_code == 200
        created = res.json()
        assert created["name"] == "demo"
        assert created["scopes"] == ["llm", "jobs"]
        assert created["key"]

        res = client.get("/apikeys")
        assert res.status_code == 200
        payload = res.json()
        assert len(payload["keys"]) == 1
        stored = payload["keys"][0]
        assert stored["name"] == "demo"
        assert stored["hash"] == "***"
        assert stored["scopes"] == ["llm", "jobs"]

        res = client.delete(f"/apikeys/{created['id']}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

        res = client.delete(f"/apikeys/{created['id']}")
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(require_jwt, None)
        app.dependency_overrides.pop(csrf_protect, None)
