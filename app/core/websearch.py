from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any, Dict, List, Tuple

try:  # pragma: no cover - compatibility shim
    from ddgs import DDGS  # type: ignore
except ImportError:  # pragma: no cover
    from duckduckgo_search import DDGS  # type: ignore
from duckduckgo_search.exceptions import RatelimitException

from app.core.config import Settings

Backends = ("duckduckgo", "lite")
_STOP_WORDS = {
    "quel",
    "quels",
    "quelle",
    "quelles",
    "quoi",
    "quand",
    "comment",
    "pourquoi",
    "est",
    "sont",
    "les",
    "des",
    "de",
    "la",
    "le",
    "du",
    "un",
    "une",
    "sur",
    "dans",
    "avec",
    "pour",
    "aujourd",
    "aujourdhui",
    "maintenant",
    "etes",
    "sommes",
    "quelleque",
    "quelques",
    "ce",
    "cette",
    "ces",
    "tout",
    "tous",
    "toutes",
}
_TOKEN_RE = re.compile(r"[0-9a-zA-Z\u00C0-\u017F']+")
_MAX_QUERY_TOKENS = 12
_MIN_EFFECTIVE_CHARS = 3
_QUESTION_TRIGGERS = {"quoi", "quel", "quels", "quelle", "quelles"}
_PLACEHOLDER_PREFIXES = ("cest quoi", "c'est quoi", "cest quel", "c'est quel", "cest quelles", "c'est quelles")


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def refine_search_query(raw_query: str) -> str:
    """Produce a query better suited for web search than the raw question."""
    text = (raw_query or "").strip()
    if not text:
        return ""
    lowered = _strip_accents(text.lower())
    tokens = [tok for tok in (_TOKEN_RE.findall(lowered) or []) if tok]
    filtered = [tok for tok in tokens if tok not in _STOP_WORDS and len(tok) > 1]
    selected = filtered or tokens
    if not selected:
        return text
    trimmed = " ".join(selected[:_MAX_QUERY_TOKENS]).strip()
    if len(trimmed) < _MIN_EFFECTIVE_CHARS:
        return text
    return trimmed


def _tokenize_query(raw_query: str) -> List[str]:
    normalized = _strip_accents((raw_query or "").strip().lower())
    return _TOKEN_RE.findall(normalized) if normalized else []


def _should_ignore_query(raw_query: str) -> Tuple[bool, str | None]:
    tokens = _tokenize_query(raw_query)
    if not tokens:
        return True, "empty_query"
    semantic_tokens = [tok for tok in tokens if tok not in _STOP_WORDS and len(tok) >= 3 and tok not in _QUESTION_TRIGGERS]
    if semantic_tokens:
        return False, None
    condensed = [tok for tok in tokens if tok not in {"c", "est", "cest"}]
    if condensed and all(tok in _QUESTION_TRIGGERS for tok in condensed):
        return True, "question_word_only"
    if len(condensed) <= 2 and any(tok in _QUESTION_TRIGGERS for tok in condensed):
        return True, "placeholder_short"
    prefix = " ".join(condensed[:3])
    if any(prefix.startswith(pattern) for pattern in _PLACEHOLDER_PREFIXES):
        return True, "placeholder_prefix"
    if not semantic_tokens:
        return True, "no_semantic_token"
    return False, None


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
    raw_query = (query or "").strip()
    if not raw_query:
        return [], {"status": "empty_query", "query": "", "normalized_query": ""}
    normalized_query = refine_search_query(raw_query)
    ignored, reason = _should_ignore_query(raw_query)
    if ignored:
        return [], {
            "status": "ignored",
            "reason": reason or "semantic_filter",
            "query": raw_query,
            "normalized_query": normalized_query,
        }
    if len(normalized_query.strip()) < _MIN_EFFECTIVE_CHARS:
        return [], {"status": "weak_query", "query": raw_query, "normalized_query": normalized_query}

    settings = Settings()
    safesearch = getattr(settings, "duckduckgo_safe_search", "moderate")
    region = getattr(settings, "duckduckgo_region", "wt-wt")

    loop = asyncio.get_running_loop()
    errors: List[dict[str, Any]] = []

    for backend in Backends:
        items, error = await loop.run_in_executor(
            None,
            _sync_search,
            normalized_query,
            backend,
            safesearch,
            region,
            max_results,
        )
        if items:
            return items, {
                "backend": backend,
                "status": "ok",
                "error": None,
                "query": raw_query,
                "normalized_query": normalized_query,
            }
        if error:
            errors.append({"backend": backend, "error": error})

    return [], {
        "backend": None,
        "status": "error",
        "errors": errors,
        "query": raw_query,
        "normalized_query": normalized_query,
    }


async def search_duckduckgo(query: str, *, max_results: int = 5) -> List[dict[str, Any]]:
    items, _meta = await _search_duckduckgo_internal(query, max_results=max_results)
    return items


async def search_duckduckgo_with_meta(query: str, *, max_results: int = 5) -> Tuple[List[dict[str, Any]], Dict[str, Any]]:
    return await _search_duckduckgo_internal(query, max_results=max_results)


async def search_duckduckgo_detailed(query: str, *, max_results: int = 5) -> dict[str, Any]:
    items, meta = await _search_duckduckgo_internal(query, max_results=max_results)
    meta.setdefault("count", len(items))
    meta.setdefault("query", (query or "").strip())
    meta.setdefault("normalized_query", refine_search_query(query or ""))
    return {"items": items, "meta": meta}

