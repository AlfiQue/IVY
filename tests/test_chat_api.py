import asyncio
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core import chat_store
from app.core.security import require_jwt_or_api_key
from app.api import routes_chat, routes_memory, routes_learning


@pytest.fixture(autouse=True)
def reset_chat_store():
    asyncio.run(chat_store.clear_all())
    yield
    asyncio.run(chat_store.clear_all())


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[require_jwt_or_api_key] = lambda: None
    app.dependency_overrides[routes_chat._chat_auth] = lambda: None
    app.dependency_overrides[routes_memory._memory_auth] = lambda: None
    app.dependency_overrides[routes_learning.require_jwt_or_api_key] = lambda: None
    yield
    app.dependency_overrides.clear()


def _patch_chat(monkeypatch):
    async def fake_embed(text: str) -> np.ndarray:
        return np.array([1.0, 0.0, 0.0], dtype=np.float32)

    async def fake_chat(self, messages: Any, **_: Any) -> dict[str, Any]:
        return {"text": "Réponse stub", "provider": "llm"}

    async def fake_class(question: str) -> dict[str, Any]:
        return {"is_variable": False, "needs_search": False, "provider": "stub"}

    def fake_heuristic(question: str) -> dict[str, Any]:
        return {"is_variable": False, "needs_search": False}

    async def fake_search(_: str, *, max_results: int = 5) -> list[dict[str, Any]]:  # noqa: ARG001
        return []

    async def fake_search_meta(_: str, *, max_results: int = 5):  # noqa: ARG001
        return [], {"backend": None, "status": "skipped", "query": "", "normalized_query": ""}

    monkeypatch.setattr('app.core.embeddings.embed_text', fake_embed)
    monkeypatch.setattr('app.core.llm.LLMClient.chat', fake_chat, raising=False)
    monkeypatch.setattr('app.core.classifier.classify_with_llm', fake_class)
    monkeypatch.setattr('app.core.classifier.classify_with_heuristic', fake_heuristic)
    monkeypatch.setattr('app.core.websearch.search_duckduckgo', fake_search)
    monkeypatch.setattr('app.core.websearch.search_duckduckgo_with_meta', fake_search_meta)


def test_chat_query_memory(monkeypatch):
    _patch_chat(monkeypatch)
    with TestClient(app) as client:
        resp1 = client.post('/chat/query', json={"question": "Bonjour"})
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["origin"] == "llm"
        conv_id = data1["conversation_id"]

        resp2 = client.post('/chat/query', json={"question": "Bonjour", "conversation_id": conv_id})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["origin"] == "database"
        assert data2["qa_id"] == data1["qa_id"]

        qa_total = asyncio.run(chat_store.count_qa())
        assert qa_total == 1


def test_memory_api(monkeypatch):
    _patch_chat(monkeypatch)
    with TestClient(app) as client:
        client.post('/chat/query', json={"question": "Bonjour"})
        resp = client.get('/memory/qa')
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        qa_id = data["items"][0]["id"]

        upd = client.patch(f'/memory/qa/{qa_id}', json={"answer": "Salut"})
        assert upd.status_code == 200
        assert upd.json()["answer"] == "Salut"

        classify = client.post(f'/memory/qa/{qa_id}/classify/llm')
        assert classify.status_code == 200
        heur = client.post(f'/memory/qa/{qa_id}/classify/heuristic')
        assert heur.status_code == 200

        dele = client.delete(f'/memory/qa/{qa_id}')
        assert dele.status_code == 200
        remaining = client.get('/memory/qa').json()
        assert qa_id not in [item["id"] for item in remaining.get("items", [])]


def test_create_conversation_writes_conversation_table():
    conv = asyncio.run(chat_store.create_conversation(" Sujet "))
    assert conv["title"] == "Sujet"
    assert "id" in conv

    fetched = asyncio.run(chat_store.get_conversation(conv["id"]))
    assert fetched is not None
    assert fetched["id"] == conv["id"]
    assert fetched["title"] == "Sujet"


def test_chat_query_includes_command_metadata(monkeypatch):
    _patch_chat(monkeypatch)
    with TestClient(app) as client:
        resp = client.post('/chat/query', json={"question": "Peux-tu ouvrir le bloc-notes ?"})
        assert resp.status_code == 200
        data = resp.json()
        metadata = data["answer_message"]["metadata"]
        assert "commands" in metadata
        commands = metadata["commands"]
        assert isinstance(commands, list) and commands
        assert commands[0]["action"] == "notepad.exe"
