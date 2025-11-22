import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core import llm as llm_module
from app.core.llm import LLMClient


@pytest.mark.asyncio
async def test_llm_llama_cpp_chat(monkeypatch):
    class DummyLlama:
        def __init__(self, model_path: str, n_ctx: int, n_gpu_layers: int) -> None:
            self.model_path = model_path
            self.n_ctx = n_ctx
            self.n_gpu_layers = n_gpu_layers

        def create_chat_completion(self, messages, **options):
            return {
                "choices": [
                    {
                        "message": {"content": f"echo:{messages[-1]['content']}"},
                        "options": options,
                    }
                ]
            }

    monkeypatch.setattr(llm_module, "Llama", DummyLlama)
    llm_module._LLM_CACHE.clear()

    settings = Settings(
        llm_provider="llama_cpp",
        llm_model_path="models/mock.gguf",
        llm_context_tokens=4096,
        llm_n_gpu_layers=2,
    )
    client = LLMClient(settings=settings)

    result = await client.chat([
        {"role": "system", "content": "system"},
        {"role": "user", "content": "ping"},
    ])

    assert result["text"].startswith("echo:ping")
    assert result["provider"] == "llama_cpp"


@pytest.mark.asyncio
async def test_llm_llama_cpp_requires_model_path(monkeypatch):
    monkeypatch.setattr(llm_module, "Llama", SimpleNamespace)
    llm_module._LLM_CACHE.clear()

    settings = Settings(llm_provider="llama_cpp", llm_model_path=None)
    client = LLMClient(settings=settings)

    with pytest.raises(RuntimeError):
        await client.chat([
            {"role": "user", "content": "ping"},
        ])
