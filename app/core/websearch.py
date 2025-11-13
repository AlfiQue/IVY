from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import RatelimitException

from app.core.config import Settings

Backends = ("duckduckgo", "lite")


def _sync_search(query: str, backend: str, safesearch: str, region: str, max_results: int) -> Tuple[List[dict[str, Any]], str | None]:
    try:
        items: List[dict[str, Any]] = []
        with DDGS() as ddgs:
            for item in ddgs.text(
                query,
                safesearch=safesearch,
                region=region,
                backend=backend,
                max_results=max_results,
            ):
                items.append(
                    {
                        "title": item.get("title"),
                        "href": item.get("href"),
                        "body": item.get("body"),
                    }
                )
                if len(items) >= max_results:
                    break
        return items, None
    except Exception as exc:  # pragma: no cover - best effort logging
        return [], exc.__class__.__name__ if not isinstance(exc, RatelimitException) else "Ratelimit"


async def _search_duckduckgo_internal(query: str, *, max_results: int = 5) -> Tuple[List[dict[str, Any]], Dict[str, Any]]:
    if not query.strip():
        return [], {"status": "empty_query"}

    settings = Settings()
    safesearch = getattr(settings, "duckduckgo_safe_search", "moderate")
    region = getattr(settings, "duckduckgo_region", "wt-wt")

    loop = asyncio.get_running_loop()
    errors: List[dict[str, Any]] = []

    for backend in Backends:
        items, error = await loop.run_in_executor(
            None,
            _sync_search,
            query,
            backend,
            safesearch,
            region,
            max_results,
        )
        if items:
            return items, {"backend": backend, "status": "ok", "error": None}
        if error:
            errors.append({"backend": backend, "error": error})

    return [], {"backend": None, "status": "error", "errors": errors}


async def search_duckduckgo(query: str, *, max_results: int = 5) -> List[dict[str, Any]]:
    items, _meta = await _search_duckduckgo_internal(query, max_results=max_results)
    return items


async def search_duckduckgo_detailed(query: str, *, max_results: int = 5) -> dict[str, Any]:
    items, meta = await _search_duckduckgo_internal(query, max_results=max_results)
    meta.setdefault("count", len(items))
    meta.setdefault("query", query)
    return {"items": items, "meta": meta}

