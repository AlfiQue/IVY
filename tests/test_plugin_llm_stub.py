from __future__ import annotations

from pathlib import Path

import pytest

from app.core import plugins
from app.core import llm as llm_module


class DummyLlm:
    def __init__(self, *args, **kwargs):
        pass

    def infer(self, prompt: str, options=None) -> str:
        return f"echo: {prompt}"


def test_llm_plugin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # stub LLM class
    monkeypatch.setattr(llm_module, "Llama", object, raising=False)
    monkeypatch.setenv("LLM_MODEL_PATH", str(tmp_path / "model.bin"))
    (tmp_path / "model.bin").write_text("")

    class Dummy( llm_module.LLM):
        def __init__(self, *a, **kw):
            pass
        def infer(self, prompt: str, options=None) -> str:  # type: ignore[override]
            return f"ok:{prompt}"

    monkeypatch.setattr(llm_module, "LLM", Dummy)

    plugins.load_plugins()
    out = plugins.run("llm", prompt="salut", options=None)
    assert out == "ok:salut"

