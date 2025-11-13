from __future__ import annotations

import asyncio
from threading import Lock
from typing import Any, Iterable, Sequence

import httpx

from app.core.config import Settings

try:
    from llama_cpp import Llama  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    Llama = None  # type: ignore


_LLM_CACHE: dict[str, Any] = {}
_LLM_CACHE_LOCK = Lock()


async def _get_llama(settings: Settings) -> Any:
    if Llama is None:
        raise RuntimeError(
            "llama-cpp-python n'est pas installe. Utilisez 'pip install llama-cpp-python'"
        )
    model_path = settings.llm_model_path
    if not model_path:
        raise RuntimeError("llm_model_path non defini")

    cached = _LLM_CACHE.get(model_path)
    if cached is not None:
        return cached

    loop = asyncio.get_running_loop()

    def _load() -> Any:
        cached_local = _LLM_CACHE.get(model_path)
        if cached_local is not None:
            return cached_local
        with _LLM_CACHE_LOCK:
            cached_again = _LLM_CACHE.get(model_path)
            if cached_again is not None:
                return cached_again
            instance_local = Llama(
                model_path=model_path,
                n_ctx=int(getattr(settings, "llm_context_tokens", 8192)),
                n_gpu_layers=int(getattr(settings, "llm_n_gpu_layers", 0)),
            )
            _LLM_CACHE[model_path] = instance_local
            return instance_local

    return await loop.run_in_executor(None, _load)


class LLMClient:
    """Client unifie pour interagir avec llama.cpp ou TensorRT-LLM."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.provider = (getattr(self.settings, "llm_provider", "llama_cpp") or "llama_cpp").lower()
        self.timeout = int(getattr(self.settings, "llm_timeout_sec", 120))
        self.default_temperature = float(getattr(self.settings, "llm_temperature", 0.7))
        self.max_tokens = int(getattr(self.settings, "llm_max_output_tokens", 512))

        if self.provider == "tensorrt_llm":
            endpoint = getattr(self.settings, "tensorrt_llm_chat_endpoint", "/v1/chat/completions") or "/v1/chat/completions"
            base_url = getattr(self.settings, "tensorrt_llm_base_url", "http://127.0.0.1:8000") or "http://127.0.0.1:8000"
            self.tensorrt_base_url = base_url.rstrip("/")
            self.tensorrt_chat_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
            self.tensorrt_model = getattr(self.settings, "tensorrt_llm_model", None)
            self.tensorrt_api_key = getattr(self.settings, "tensorrt_llm_api_key", None)
            extra_headers = getattr(self.settings, "tensorrt_llm_extra_headers", {}) or {}
            self.tensorrt_extra_headers = dict(extra_headers)
        elif self.provider == "llama_cpp":
            self.llama_model_path = getattr(self.settings, "llm_model_path", None)
        else:
            raise RuntimeError(f"Fournisseur LLM inconnu: {self.provider}")

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not messages:
            raise ValueError("messages vides")
        if self.provider == "llama_cpp":
            return await self._chat_llama_cpp(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_options=extra_options,
            )
        if self.provider == "tensorrt_llm":
            return await self._chat_tensorrt_llm(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_options=extra_options,
            )
        raise RuntimeError(f"Fournisseur LLM inconnu: {self.provider}")

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    async def _chat_llama_cpp(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None,
        max_tokens: int | None,
        extra_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        llama = await _get_llama(self.settings)
        options = dict(extra_options or {})
        options.setdefault("temperature", temperature if temperature is not None else self.default_temperature)
        options.setdefault("max_tokens", max_tokens if max_tokens is not None else self.max_tokens)

        loop = asyncio.get_running_loop()

        def _run() -> dict[str, Any]:
            return llama.create_chat_completion(messages=list(messages), **options)

        data = await loop.run_in_executor(None, _run)
        choice = (data.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content", "")
        return {
            "text": content,
            "raw": data,
            "provider": "llama_cpp",
        }

    async def _chat_tensorrt_llm(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None,
        max_tokens: int | None,
        extra_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self.tensorrt_model:
            raise RuntimeError("tensorrt_llm_model non defini")
        url = f"{self.tensorrt_base_url}{self.tensorrt_chat_endpoint}"
        payload: dict[str, Any] = {
            "model": self.tensorrt_model,
            "messages": list(messages),
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": False,
        }
        if extra_options:
            payload.update(extra_options)
        headers = {"Content-Type": "application/json"}
        headers.update(self.tensorrt_extra_headers)
        if self.tensorrt_api_key:
            headers["Authorization"] = f"Bearer {self.tensorrt_api_key}"
        timeout = httpx.Timeout(self.timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip() or exc.response.reason_phrase or "HTTP error"
                raise RuntimeError(
                    "TensorRT-LLM a repondu "
                    f"{exc.response.status_code} {exc.response.reason_phrase}. "
                    "Verifiez que le serveur TensorRT-LLM est demarre et accessible.\n"
                    f"Reponse: {detail}"
                ) from exc
            except httpx.RequestError as exc:
                raise RuntimeError(
                    "Impossible de contacter TensorRT-LLM. Verifiez l'adresse tensorrt_llm_base_url."
                ) from exc
            data = resp.json()
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        content = message.get("content")
        if not content:
            content = choice.get("text") or ""
        if not content and "delta" in choice:
            content = choice["delta"].get("content", "")
        return {
            "text": content or "",
            "raw": data,
            "provider": "tensorrt_llm",
        }


def build_chat_messages(
    *,
    system: str | None = None,
    history: Iterable[tuple[str, str]] | None = None,
    prompt: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if history:
        for role, content in history:
            role_norm = role if role in {"user", "assistant", "system"} else "user"
            messages.append({"role": role_norm, "content": content})
    messages.append({"role": "user", "content": prompt})
    return messages
