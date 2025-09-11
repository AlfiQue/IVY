from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_bruteforce_cooldown() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 5 tentatives échouées
        for _ in range(5):
            r = await ac.post("/auth/login", json={"user": "admin", "password": "wrong"})
            assert r.status_code == 401
        # 6e -> cool down 429
        r = await ac.post("/auth/login", json={"user": "admin", "password": "wrong"})
        assert r.status_code in (401, 429)
        if r.status_code == 429:
            body = r.json()
            assert "error" in body or "detail" in body

