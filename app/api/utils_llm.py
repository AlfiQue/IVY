from __future__ import annotations

from typing import Any

from app.core.config import Settings

_ALLOWED_OPTIONS = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "top_k": (1, 1000),
    "repeat_penalty": (0.0, 4.0),
    "presence_penalty": (-2.0, 2.0),
    "frequency_penalty": (-2.0, 2.0),
    "max_tokens": None,
}

MAX_HISTORY_CHARS = 6000
TRUNCATE_FIELD_CHARS = 2000


def _clamp(value: Any, bounds: tuple[float, float] | tuple[int, int]) -> Any:
    low, high = bounds
    if not isinstance(value, (int, float)):
        return value
    return max(low, min(high, value))


def validate_llm_options(options: dict[str, Any], settings: Settings) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in (options or {}).items():
        if key not in _ALLOWED_OPTIONS:
            continue
        if key == "max_tokens":
            try:
                sanitized[key] = min(int(value), int(settings.llm_max_output_tokens))
            except Exception:
                sanitized[key] = settings.llm_max_output_tokens
            continue
        bounds = _ALLOWED_OPTIONS[key]
        if bounds is None:
            sanitized[key] = value
            continue
        sanitized[key] = _clamp(value, bounds)
    if "max_tokens" not in sanitized:
        sanitized["max_tokens"] = settings.llm_max_output_tokens
    return sanitized


def truncate_history(parts: list[str], max_chars: int = MAX_HISTORY_CHARS) -> list[str]:
    budget = max_chars
    truncated: list[str] = []
    for part in parts:
        if budget <= 0:
            break
        slice_part = part[:budget]
        truncated.append(slice_part)
        budget -= len(slice_part)
    return truncated


def truncate_field(value: Any, max_chars: int = TRUNCATE_FIELD_CHARS) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars]
    return value
