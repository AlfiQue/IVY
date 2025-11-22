from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Iterable, Sequence

import httpx

from app.core.config import Settings
from app.core import plugins

try:
    from llama_cpp import Llama  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    Llama = None  # type: ignore


_LLM_CACHE: dict[str, Any] = {}
_LLM_LOCK = asyncio.Lock()

logger = logging.getLogger(__name__)


def _extract_token(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        choices = payload.get("choices") or []
        if not choices:
            return ""
        choice = choices[0]
        text = choice.get("text")
        if text:
            return str(text)
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if content:
            return str(content)
        message = choice.get("message") or {}
        content = message.get("content")
        if content:
            return str(content)
    return ""


def _call_llama_chat(
    backend: Any,
    *,
    messages: Sequence[dict[str, str]],
    stream: bool,
    **options: Any,
) -> Any:
    if hasattr(backend, "create_chat_completion"):
        return backend.create_chat_completion(messages=messages, stream=stream, **options)
    if callable(backend):
        prompt = ""
        if messages:
            prompt = messages[-1].get("content", "") or ""
        call_options = dict(options)
        max_tokens = call_options.pop("max_tokens", None)
        return backend(prompt, max_tokens=max_tokens, stream=stream, **call_options)
    raise AttributeError("Llama backend does not expose a compatible chat interface")

async def _get_llama(
    settings: Settings,
    *,
    model_path: str | None = None,
    cache_label: str = "primary",
    n_ctx: int | None = None,
    n_gpu_layers: int | None = None,
) -> Any:
    if Llama is None:
        raise RuntimeError(
            "llama-cpp-python n'est pas installÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©. Utilisez 'pip install llama-cpp-python'"
        )
    path = model_path or getattr(settings, "llm_model_path", None)
    if not path:
        raise RuntimeError("llm_model_path non dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©fini")
    ctx_size = int(n_ctx if n_ctx is not None else getattr(settings, "llm_context_tokens", 8192))
    gpu_layers = int(n_gpu_layers if n_gpu_layers is not None else getattr(settings, "llm_n_gpu_layers", 0))
    cache_id = f"{cache_label}:{path}:{ctx_size}:{gpu_layers}"

    async with _LLM_LOCK:
        cached = _LLM_CACHE.get(cache_id)
        if cached is not None:
            return cached

        loop = asyncio.get_running_loop()

        def _load() -> Any:
            return Llama(
                model_path=path,
                n_ctx=ctx_size,
                n_gpu_layers=gpu_layers,
            )

        instance = await loop.run_in_executor(None, _load)
        _LLM_CACHE[cache_id] = instance
        return instance


class LLM:
    """Wrapper simple autour de llama.cpp pour les appels directs."""

    def __init__(self, model_path: str | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.model_path = model_path or getattr(self.settings, "llm_model_path", None)
        if not self.model_path:
            raise RuntimeError("LLM_MODEL_PATH non dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©fini")
        self._llama: Any | None = None

    def _load_llama(self) -> Any:
        if Llama is None:
            raise RuntimeError(
                "llama-cpp-python n'est pas installÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©. Utilisez 'pip install llama-cpp-python'"
            )
        if self._llama is None:
            self._llama = Llama(
                model_path=self.model_path,
                n_ctx=int(getattr(self.settings, "llm_context_tokens", 8192)),
                n_gpu_layers=int(getattr(self.settings, "llm_n_gpu_layers", 0)),
            )
        return self._llama

    def _prepare_options(self, options: dict[str, Any] | None) -> dict[str, Any]:
        sanitized = dict(options or {})
        sanitized.setdefault("max_tokens", int(getattr(self.settings, "llm_max_output_tokens", 512)))
        sanitized.setdefault("temperature", float(getattr(self.settings, "llm_temperature", 0.7)))
        sanitized.setdefault("stream", True)
        return sanitized

    def infer(self, prompt: str, options: dict[str, Any] | None = None) -> list[str]:
        llama = self._load_llama()
        opts = self._prepare_options(options)
        opts["stream"] = True
        messages = [{"role": "user", "content": prompt}]
        tokens: list[str] = []
        try:
            for chunk in _call_llama_chat(
                llama,
                messages=messages,
                stream=True,
                **{k: v for k, v in opts.items() if k != "stream"},
            ):
                token = _extract_token(chunk)
                if token:
                    tokens.append(token)
        except Exception:
            # fallback en mode non streaming
            opts["stream"] = False
            data = _call_llama_chat(
                llama,
                messages=messages,
                stream=False,
                **{k: v for k, v in opts.items() if k != "stream"},
            )
            token = _extract_token(data)
            if token:
                tokens.append(token)
        if not tokens:
            tokens.append("")
        return tokens

    async def astream(self, prompt: str, options: dict[str, Any] | None = None) -> Iterable[str]:
        llama = self._load_llama()
        opts = self._prepare_options(options)
        opts["stream"] = True
        messages = [{"role": "user", "content": prompt}]
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()

        def worker() -> None:
            try:
                call_kwargs = {k: v for k, v in opts.items() if k != "stream"}
                try:
                    iterator = _call_llama_chat(llama, messages=messages, stream=True, **call_kwargs)
                except Exception:
                    iterator = _call_llama_chat(llama, messages=messages, stream=False, **call_kwargs)
                if isinstance(iterator, dict):
                    iterator = [iterator]
                for chunk in iterator:
                    token = _extract_token(chunk)
                    if token:
                        loop.call_soon_threadsafe(queue.put_nowait, token)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item


class LLMClient:
    """Client unifiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© pour interagir avec llama.cpp ou TensorRT-LLM."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.provider = (getattr(self.settings, "llm_provider", "llama_cpp") or "llama_cpp").lower()
        self.timeout = int(getattr(self.settings, "llm_timeout_sec", 120))
        self.default_temperature = float(getattr(self.settings, "llm_temperature", 0.7))
        self.max_tokens = int(getattr(self.settings, "llm_max_output_tokens", 512))
        self.speculative_enabled = bool(getattr(self.settings, "llm_speculative_enabled", False))
        self.speculative_model_path = getattr(self.settings, "llm_speculative_model_path", None)
        self.speculative_max_draft_tokens = int(getattr(self.settings, "llm_speculative_max_draft_tokens", 64))
        self.speculative_context_tokens = getattr(self.settings, "llm_speculative_context_tokens", None)
        self.speculative_n_gpu_layers = getattr(self.settings, "llm_speculative_n_gpu_layers", None)
        if not self.speculative_model_path:
            self.speculative_enabled = False
        if self.speculative_context_tokens is None:
            self.speculative_context_tokens = getattr(self.settings, "llm_context_tokens", None)
        if self.speculative_n_gpu_layers is None:
            self.speculative_n_gpu_layers = getattr(self.settings, "llm_n_gpu_layers", None)

        if self.provider != "llama_cpp":
            self.speculative_enabled = False

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
        llama = await _get_llama(
            self.settings,
            model_path=self.llama_model_path,
            cache_label="primary",
        )
        options = dict(extra_options or {})
        options.setdefault("temperature", temperature if temperature is not None else self.default_temperature)
        options.setdefault("max_tokens", max_tokens if max_tokens is not None else self.max_tokens)

        draft_model: Any | None = None
        if self.speculative_enabled and self.speculative_model_path:
            try:
                draft_model = await _get_llama(
                    self.settings,
                    model_path=self.speculative_model_path,
                    cache_label="speculative",
                    n_ctx=self.speculative_context_tokens,
                    n_gpu_layers=self.speculative_n_gpu_layers,
                )
            except Exception as exc:  # pragma: no cover - environnement runtime
                logger.warning("Speculative decoding d\u00e9sactiv\u00e9: %s", exc)

        loop = asyncio.get_running_loop()

        def _run() -> tuple[dict[str, Any], bool]:
            used_speculative = False
            call_kwargs = dict(options)
            if draft_model is not None:
                call_kwargs["speculative"] = {
                    "model": draft_model,
                    "max_draft_tokens": self.speculative_max_draft_tokens,
                }
            try:
                data = llama.create_chat_completion(messages=list(messages), **call_kwargs)
                used_speculative = draft_model is not None
            except TypeError:
                logger.info("Version de llama.cpp sans mode speculative; retour standard")
                data = llama.create_chat_completion(messages=list(messages), **options)
            except AttributeError:
                # compatibilité avec les doubles stubs utilisés en tests
                call_kwargs.pop("speculative", None)
                data = _call_llama_chat(
                    llama,
                    messages=list(messages),
                    stream=False,
                    **call_kwargs,
                )
                used_speculative = False
            except Exception as exc:  # pragma: no cover - runtime dependant
                logger.warning("Echec du mode speculative: %s", exc)
                data = llama.create_chat_completion(messages=list(messages), **options)
            return data, used_speculative

        data, used_speculative = await loop.run_in_executor(None, _run)
        choice = (data.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content", "")
        return {
            "text": content,
            "raw": data,
            "provider": "llama_cpp",
            "speculative": used_speculative,
        }


    async def _chat_tensorrt_llm(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None,
        max_tokens: int | None,
        extra_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not getattr(self, "tensorrt_model", None):
            raise RuntimeError("tensorrt_llm_model non dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©fini")
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
        headers.update(getattr(self, "tensorrt_extra_headers", {}))
        if getattr(self, "tensorrt_api_key", None):
            headers["Authorization"] = f"Bearer {self.tensorrt_api_key}"
        timeout = httpx.Timeout(self.timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = resp.text.strip() or resp.reason_phrase or "HTTP error"
                raise RuntimeError(
                    "TensorRT-LLM a rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©pondu "
                    f"{exc.response.status_code} {exc.response.reason_phrase}. "
                    "VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rifiez que le serveur TensorRT-LLM est dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©marrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© et accessible.\n"
                    f"RÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ponse: {detail}"
                ) from exc
            except httpx.RequestError as exc:
                raise RuntimeError(
                    "Impossible de contacter TensorRT-LLM. VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rifiez l'adresse tensorrt_llm_base_url."
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


# Exposer le module plugins pour compatibilite avec les tests
