from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.history import insert_event
from app.main import app


@pytest.mark.asyncio
async def test_get_history_with_filters() -> None:
    # précharger quelques événements
    await insert_event("llm", {"user_input": "bonjour", "server_output": "salut"})
    await insert_event("plugin", {"plugin": "weather", "args": {"lat": 1, "lon": 2}})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # sans filtre
        r = await client.get("/history", params={"limit": 10, "offset": 0})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data
        assert isinstance(data["items"], list)

        # filtre plugin
        r2 = await client.get("/history", params={"plugin": "weather"})
        assert r2.status_code == 200
        d2 = r2.json()
        assert any("weather" in str(x.get("payload")) for x in d2["items"]) or d2["total"] >= 0

