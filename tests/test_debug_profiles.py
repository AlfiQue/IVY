from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.llm import LLMClient
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


async def _stub_chat(
    self: LLMClient,
    messages,
    *,
    temperature=None,
    max_tokens=None,
    extra_options=None,
) -> dict[str, Any]:
    calls = getattr(_stub_chat, "_calls", None)
    if calls is None:
        calls = []
        setattr(_stub_chat, "_calls", calls)
    calls.append(
        {
            "speculative": getattr(self, "speculative_enabled", False),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "options": dict(extra_options or {}),
            "message_count": len(messages),
        }
    )
    return {
        "text": f"sample-{len(calls)}",
        "raw": {"usage": {"prompt_tokens": 12, "completion_tokens": 6}},
        "speculative": getattr(self, "speculative_enabled", False),
    }


def _reset_stub() -> None:
    if hasattr(_stub_chat, "_calls"):
        delattr(_stub_chat, "_calls")


def _get_calls() -> list[dict[str, Any]]:
    return getattr(_stub_chat, "_calls", [])


def test_benchmark_profiles_success(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _reset_stub()
    monkeypatch.setattr(LLMClient, "chat", _stub_chat, raising=False)

    payload = {
        "prompt": "Donne un resume du livre",
        "profiles": [
            {
                "name": "Standard",
                "description": "Sans draft",
                "samples": 2,
                "settings": {"llm_context_tokens": 4096, "llm_speculative_enabled": False},
                "options": {"temperature": 0.6, "top_p": 0.92, "max_tokens": 256},
            },
            {
                "name": "Spec",
                "samples": 1,
                "settings": {"llm_speculative_enabled": True, "llm_speculative_model_path": "draft.gguf"},
                "options": {"temperature": 0.4, "top_k": 40},
            },
        ],
    }

    res = client.post("/debug/llm-profiles", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["prompt"] == "Donne un resume du livre"
    assert len(data["profiles"]) == 2

    calls = _get_calls()
    assert len(calls) == 3
    assert calls[0]["speculative"] is False
    assert calls[0]["temperature"] == pytest.approx(0.6)
    assert calls[0]["max_tokens"] == 256
    assert calls[0]["options"].get("top_p") == pytest.approx(0.92)
    assert calls[2]["speculative"] is True
    assert calls[2]["options"].get("top_k") == 40

    standard = data["profiles"][0]
    assert standard["name"] == "Standard"
    assert standard["samples"] == 2
    assert standard["applied_settings"]["llm_speculative_enabled"] is False
    assert len(standard["runs"]) == 2
    assert standard["runs"][0]["text"].startswith("sample-")
    assert standard["runs"][0]["usage"]["prompt_tokens"] == 12

    spec = data["profiles"][1]
    assert spec["applied_settings"]["llm_speculative_enabled"] is True
    assert spec["applied_settings"]["llm_speculative_model_path"] == "draft.gguf"
    assert spec["runs"][0]["speculative"] is True
    assert spec["runs"][0]["text"].startswith("sample-")


async def _stub_chat_with_failure(
    self: LLMClient,
    messages,
    *,
    temperature=None,
    max_tokens=None,
    extra_options=None,
) -> dict[str, Any]:
    calls = getattr(_stub_chat_with_failure, "_calls", 0)
    setattr(_stub_chat_with_failure, "_calls", calls + 1)
    if calls == 0:
        raise RuntimeError("draft unavailable")
    return {
        "text": "ok",
        "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 4}},
        "speculative": getattr(self, "speculative_enabled", False),
    }


def test_benchmark_profiles_partial_failure(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    if hasattr(_stub_chat_with_failure, "_calls"):
        delattr(_stub_chat_with_failure, "_calls")
    monkeypatch.setattr(LLMClient, "chat", _stub_chat_with_failure, raising=False)

    payload = {
        "prompt": "Analyse en deux essais",
        "profiles": [
            {
                "name": "SpecFail",
                "samples": 2,
                "settings": {"llm_speculative_enabled": True},
                "options": {"temperature": 0.5},
            }
        ],
    }

    res = client.post("/debug/llm-profiles", json=payload)
    assert res.status_code == 200
    data = res.json()
    profile = data["profiles"][0]
    assert len(profile["runs"]) == 1
    assert len(profile["errors"]) == 1
    assert "draft unavailable" in profile["errors"][0]
    assert profile["runs"][0]["text"] == "ok"
    assert profile["runs"][0]["speculative"] is True
