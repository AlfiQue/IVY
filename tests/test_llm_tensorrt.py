import json
import pytest
import httpx

from app.core.config import Settings
from app.core.llm import LLMClient


@pytest.mark.asyncio
async def test_llm_tensorrt_requires_model():
    settings = Settings(llm_provider="tensorrt_llm", tensorrt_llm_model=None)
    client = LLMClient(settings=settings)
    with pytest.raises(RuntimeError):
        await client.chat([{"role": "user", "content": "ping"}])


@pytest.mark.asyncio
async def test_llm_tensorrt_chat_success(monkeypatch):
    captured: dict[str, object] = {}

    class DummyResponse:
        status_code = 200
        reason_phrase = "OK"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "pong"}}]}

        @property
        def text(self) -> str:
            return json.dumps(self.json())

    class DummyClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, *, json: dict[str, object] | None = None, headers: dict[str, str] | None = None):
            captured["url"] = url
            captured["payload"] = json or {}
            captured["headers"] = headers or {}
            return DummyResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: DummyClient(*args, **kwargs))

    settings = Settings(
        llm_provider="tensorrt_llm",
        tensorrt_llm_model="demo-model",
        tensorrt_llm_base_url="http://localhost:8999",
        tensorrt_llm_chat_endpoint="chat/completions",
        tensorrt_llm_api_key="secret-key",
        tensorrt_llm_extra_headers={"X-Test": "1"},
        llm_max_output_tokens=42,
    )
    client = LLMClient(settings=settings)
    result = await client.chat([{"role": "user", "content": "ping"}], temperature=0.5, max_tokens=16)

    assert result["text"] == "pong"
    assert result["provider"] == "tensorrt_llm"
    assert captured["url"] == "http://localhost:8999/chat/completions"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "demo-model"
    assert payload["temperature"] == 0.5
    assert payload["max_tokens"] == 16
    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer secret-key"
    assert headers["X-Test"] == "1"
