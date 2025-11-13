from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.history import insert_event
from app.main import app


@pytest.mark.asyncio
async def test_get_history_with_filters() -> None:
    await insert_event("llm", {"user_input": "bonjour", "server_output": "salut"})
    await insert_event("system", {"info": "test"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/auth/login", json={"user": "admin", "password": "admin"})
        assert login.status_code == 200

        r = await client.get("/history", params={"limit": 10, "offset": 0})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data
        assert isinstance(data["items"], list)

        r2 = await client.get("/history", params={"q": "bonjour"})
        assert r2.status_code == 200
        d2 = r2.json()
        assert any("bonjour" in str(item.get("payload")) for item in d2.get("items", []))
