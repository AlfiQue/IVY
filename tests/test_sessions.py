from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.sessions import create_session
from app.main import app


@pytest.mark.asyncio
async def test_sessions_list_and_terminate() -> None:
    s = create_session("webui")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/sessions")
        assert res.status_code == 200
        data = res.json()
        assert any(sess["id"] == s.id for sess in data["sessions"])  # type: ignore[index]

        res2 = await ac.post(f"/sessions/{s.id}/terminate")
        assert res2.status_code == 200

