import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.core.rate_limit import rate_limit_middleware  # noqa: E402


@pytest.mark.asyncio
async def test_rate_limit_returns_429_when_exceeded() -> None:
    rps = 5
    app = FastAPI()
    app.middleware("http")(rate_limit_middleware(rps))

    @app.get("/")
    async def _() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(rps):
            resp = await client.get("/")
            assert resp.status_code == 200
        with pytest.raises(HTTPException) as exc:
            await client.get("/")
    assert exc.value.status_code == 429
