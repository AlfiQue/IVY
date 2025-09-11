from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from threading import Thread
from typing import Any, AsyncIterator, Iterator

from llama_cpp import Llama

from . import plugins


class LLM:
    """Interface simple autour de :class:`llama_cpp.Llama`.

    Le modèle est chargé depuis ``model_path`` (souvent défini via la
    variable d'environnement ``LLM_MODEL_PATH``) avec un contexte de 16k et
    une génération limitée à 1024 tokens.
    """

    def __init__(self, model_path: str | Path | None = None, **kwargs: Any) -> None:
        if model_path is None:
            model_path = os.environ.get("LLM_MODEL_PATH")
        if not model_path:
            raise ValueError("Chemin du modèle non défini")
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"Modèle introuvable: {path}")
        self._llama = Llama(model_path=str(path), n_ctx=16_384, **kwargs)
        self._plugins = plugins.load_plugins()

    def _invoke(self, prompt: str, stream: bool, options: dict | None) -> Any:
        params = {"max_tokens": 1024, "stream": stream}
        if options:
            params.update(options)
        return self._llama(prompt, **params)

    def _maybe_call_plugin(self, candidate: str) -> str | None:
        candidate = candidate.strip()
        if not (candidate.startswith("{") and candidate.endswith("}")):
            return None
        try:
            data = json.loads(candidate)
        except ValueError:
            return None
        name = data.get("name")
        args = data.get("arguments", {})
        meta = self._plugins.get(name)
        if not meta:
            return None
        schema = meta.get("inputs", {}).get("schema")
        if schema:
            args = schema(**args).model_dump()
        result = plugins.run(name, **args)
        return str(result)

    def stream(self, prompt: str, options: dict | None = None) -> Iterator[str]:
        """Générer les tokens un par un."""

        buffer = ""
        for chunk in self._invoke(prompt, True, options):
            token = chunk["choices"][0]["text"]
            buffer += token
            plugin_result = self._maybe_call_plugin(buffer)
            if plugin_result is not None:
                yield plugin_result
                buffer = ""
            elif not buffer.strip().startswith("{"):
                yield buffer
                buffer = ""

        if buffer:
            plugin_result = self._maybe_call_plugin(buffer)
            if plugin_result is not None:
                yield plugin_result
            else:
                yield buffer

    async def astream(
        self, prompt: str, options: dict | None = None
    ) -> AsyncIterator[str]:
        """Version asynchrone de :meth:`stream`."""

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[object] = asyncio.Queue()

        def _worker() -> None:
            try:
                for tok in self.stream(prompt, options):
                    asyncio.run_coroutine_threadsafe(queue.put(tok), loop)
            except Exception as exc:  # pragma: no cover - géré dans l'async
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        Thread(target=_worker, daemon=True).start()

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item  # type: ignore[misc]

    def infer(self, prompt: str, options: dict | None = None) -> str:
        """Retourne la réponse complète pour ``prompt``."""

        return "".join(self.stream(prompt, options))

    async def ainfer(self, prompt: str, options: dict | None = None) -> str:
        """Version asynchrone de :meth:`infer`."""

        chunks = []
        async for tok in self.astream(prompt, options):
            chunks.append(tok)
        return "".join(chunks)
