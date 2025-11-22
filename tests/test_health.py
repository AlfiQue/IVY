import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok() -> None:
    Path("app/data/faiss_index").mkdir(parents=True, exist_ok=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")

    assert response.status_code == 200
    data = response.json()
    expected = {"status", "version", "time", "gpu", "plugins_count", "db_ok", "faiss_ok"}
    assert expected <= data.keys()
    assert data["db_ok"] is True
    assert data["faiss_ok"] is True
    assert isinstance(data["plugins_count"], int)
