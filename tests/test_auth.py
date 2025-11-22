import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.main import app


@pytest.mark.asyncio
async def test_login_logout_csrf() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/login", json={"user": "admin", "password": "admin"}
        )
        assert resp.status_code == 200
        csrf = resp.json()["csrf_token"]
        assert "access_token" in resp.cookies

        resp = await client.post("/history/replay")
        assert resp.status_code == 403

        headers = {"X-CSRF-Token": csrf}
        resp = await client.post("/history/replay", headers=headers)
        assert resp.status_code == 200

        resp = await client.post("/auth/logout", headers=headers)
        assert resp.status_code == 200
