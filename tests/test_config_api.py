from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes_config
from app.core import config as config_module
from app.core.config import get_settings
from app.core.security import csrf_protect, require_jwt
from app.main import app


def test_config_routes_apply_and_mask(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "tests-secret-value-config")

    def _custom_source() -> dict[str, object]:
        path = tmp_path / "config.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    monkeypatch.setattr(routes_config, "_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(
        config_module.Settings,
        "json_config_settings_source",
        staticmethod(_custom_source),
        raising=False,
    )
    get_settings.cache_clear()  # type: ignore[attr-defined]

    app.dependency_overrides[require_jwt] = lambda: None
    app.dependency_overrides[csrf_protect] = lambda: None
    client = TestClient(app)
    try:
        res = client.get("/config")
        assert res.status_code == 200
        data = res.json()
        assert data["jwt_secret"] == "***"
        assert "duckduckgo.com" in data.get("allowlist_domains", [])

        res = client.put("/config", json={"rate_limit_rps": 42, "jwt_secret": "super-secret"})
        assert res.status_code == 200
        updated = res.json()
        assert updated["rate_limit_rps"] == 42
        assert updated["jwt_secret"] == "***"

        persisted = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert persisted["jwt_secret"] == "super-secret"
        assert persisted["rate_limit_rps"] == 42

        get_settings.cache_clear()  # type: ignore[attr-defined]
        final_settings = get_settings()
        assert final_settings.rate_limit_rps == 42
    finally:
        app.dependency_overrides.pop(require_jwt, None)
        app.dependency_overrides.pop(csrf_protect, None)
        get_settings.cache_clear()  # type: ignore[attr-defined]
        monkeypatch.delenv("JWT_SECRET", raising=False)
