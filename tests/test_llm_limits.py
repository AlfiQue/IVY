from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_llm_infer_too_long_input_returns_4101() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        long_prompt = "x" * (8000 * 5)  # approx > 8000 tokens
        r = await ac.post("/llm/infer", json={"prompt": long_prompt})
        assert r.status_code == 400
        body = r.json()
        # body may wrap error in {error:{...}} or detail
        assert "error" in body or "detail" in body

