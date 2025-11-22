from __future__ import annotations

import asyncio
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import Settings


@lru_cache()
def _model_name() -> str:
    settings = Settings()
    return getattr(settings, "embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2") or "sentence-transformers/all-MiniLM-L6-v2"


_model: SentenceTransformer | None = None
_model_lock = asyncio.Lock()


async def _get_model() -> SentenceTransformer:
    global _model
    if _model is not None:
        return _model
    async with _model_lock:
        if _model is None:
            loop = asyncio.get_running_loop()
            name = _model_name()
            def _load() -> SentenceTransformer:
                return SentenceTransformer(name)
            _model = await loop.run_in_executor(None, _load)
    return _model


async def embed_text(text: str) -> np.ndarray:
    model = await _get_model()
    loop = asyncio.get_running_loop()
    def _encode() -> np.ndarray:
        vec = model.encode([text], normalize_embeddings=True)
        return vec[0].astype(np.float32)
    return await loop.run_in_executor(None, _encode)

