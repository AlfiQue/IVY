from pathlib import Path
from typing import List

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from app.core import llm as llm_module
from app.main import app


class DummyLlama:
    tokens: List[str] = []

    def __init__(self, model_path: str, n_ctx: int, **kwargs: object) -> None:
        self.model_path = model_path

    def __call__(self, prompt: str, max_tokens: int, stream: bool, **_: object):
        if stream:
            for tok in self.tokens:
                yield {"choices": [{"text": tok}]}
        else:
            return {"choices": [{"text": "".join(self.tokens)}]}


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    model = tmp_path / "model.bin"
    model.write_text("")
    monkeypatch.setenv("LLM_MODEL_PATH", str(model))
    monkeypatch.setattr(llm_module, "Llama", DummyLlama)


def test_infer_simple(monkeypatch: pytest.MonkeyPatch) -> None:
    DummyLlama.tokens = ["salut"]
    monkeypatch.setattr(llm_module.plugins, "load_plugins", lambda: {})
    client = TestClient(app)
    res = client.post("/llm/infer", json={"prompt": "hi"})
    assert res.status_code == 200
    assert res.json() == {"text": "salut"}
    with client.websocket_connect("/llm/stream") as ws:
        ws.send_json(
            {
                "type": "request",
                "req_id": "1",
                "source": "client",
                "event": "start",
                "payload": {"prompt": "hi"},
                "ts": 0,
            }
        )
        msg = ws.receive_json()
        assert msg["event"] == "token"
        assert msg["payload"] == "salut"
        end = ws.receive_json()
        assert end["event"] == "end"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_infer_with_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    DummyLlama.tokens = ['{"name":"weather","arguments":{"lat":1,"lon":2}}']

    class Weather(BaseModel):
        lat: int
        lon: int

    monkeypatch.setattr(
        llm_module.plugins,
        "load_plugins",
        lambda: {"weather": {"inputs": {"schema": Weather}}},
    )
    monkeypatch.setattr(
        llm_module.plugins, "run", lambda name, **args: "ensoleillé", raising=False
    )
    client = TestClient(app)
    res = client.post("/llm/infer", json={"prompt": "hi"})
    assert res.status_code == 200
    assert res.json() == {"text": "ensoleillé"}
    with client.websocket_connect("/llm/stream") as ws:
        ws.send_json(
            {
                "type": "request",
                "req_id": "2",
                "source": "client",
                "event": "start",
                "payload": {"prompt": "hi"},
                "ts": 0,
            }
        )
        msg = ws.receive_json()
        assert msg["payload"] == "ensoleillé"
        end = ws.receive_json()
        assert end["event"] == "end"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_invalid_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    DummyLlama.tokens = ['{"name":"weather","arguments":{"lat":"bad","lon":2}}']

    class Weather(BaseModel):
        lat: int
        lon: int

    monkeypatch.setattr(
        llm_module.plugins,
        "load_plugins",
        lambda: {"weather": {"inputs": {"schema": Weather}}},
    )
    client = TestClient(app)
    res = client.post("/llm/infer", json={"prompt": "hi"})
    assert res.status_code == 400


def test_missing_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    DummyLlama.tokens = ['{"name":"weather","arguments":{"lat":1,"lon":2}}']
    monkeypatch.setattr(llm_module.plugins, "load_plugins", lambda: {})
    client = TestClient(app)
    res = client.post("/llm/infer", json={"prompt": "hi"})
    assert res.status_code == 200
    assert res.json()["text"].startswith('{"name"')


def test_missing_plugin_ws(monkeypatch: pytest.MonkeyPatch) -> None:
    DummyLlama.tokens = ['{"name":"weather","arguments":{"lat":1,"lon":2}}']
    monkeypatch.setattr(llm_module.plugins, "load_plugins", lambda: {})
    client = TestClient(app)
    with client.websocket_connect("/llm/stream") as ws:
        ws.send_json(
            {
                "type": "request",
                "req_id": "4",
                "source": "client",
                "event": "start",
                "payload": {"prompt": "hi"},
                "ts": 0,
            }
        )
        msg = ws.receive_json()
        assert msg["event"] == "token"
        assert msg["payload"].startswith('{"name"')
        end = ws.receive_json()
        assert end["event"] == "end"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_plugin_mixed_with_text(monkeypatch: pytest.MonkeyPatch) -> None:
    DummyLlama.tokens = [
        "Bonjour ",
        '{"name":"weather","arguments":{"lat":1,"lon":2}}',
        " !",
    ]

    class Weather(BaseModel):
        lat: int
        lon: int

    monkeypatch.setattr(
        llm_module.plugins,
        "load_plugins",
        lambda: {"weather": {"inputs": {"schema": Weather}}},
    )

    def run(name: str, **args: object) -> str:
        assert name == "weather"
        assert args == {"lat": 1, "lon": 2}
        return "ensoleillé"

    monkeypatch.setattr(llm_module.plugins, "run", run)

    client = TestClient(app)
    res = client.post("/llm/infer", json={"prompt": "hi"})
    assert res.status_code == 200
    assert res.json() == {"text": "Bonjour ensoleillé !"}

    with client.websocket_connect("/llm/stream") as ws:
        ws.send_json(
            {
                "type": "request",
                "req_id": "3",
                "source": "client",
                "event": "start",
                "payload": {"prompt": "hi"},
                "ts": 0,
            }
        )
        msg = ws.receive_json()
        assert msg["event"] == "token"
        assert msg["payload"] == "Bonjour "
        msg = ws.receive_json()
        assert msg["event"] == "token"
        assert msg["payload"] == "ensoleillé"
        msg = ws.receive_json()
        assert msg["event"] == "token"
        assert msg["payload"] == " !"
        end = ws.receive_json()
        assert end["event"] == "end"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_invalid_schema_ws(monkeypatch: pytest.MonkeyPatch) -> None:
    DummyLlama.tokens = ['{"name":"weather","arguments":{"lat":"bad","lon":2}}']

    class Weather(BaseModel):
        lat: int
        lon: int

    monkeypatch.setattr(
        llm_module.plugins,
        "load_plugins",
        lambda: {"weather": {"inputs": {"schema": Weather}}},
    )
    client = TestClient(app)
    with client.websocket_connect("/llm/stream") as ws:
        ws.send_json(
            {
                "type": "request",
                "req_id": "5",
                "source": "client",
                "event": "start",
                "payload": {"prompt": "hi"},
                "ts": 0,
            }
        )
        msg = ws.receive_json()
        assert msg["event"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
