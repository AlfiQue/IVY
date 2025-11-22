from __future__ import annotations

import logging
import time
from typing import Any, Literal, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from app.api.utils_llm import truncate_field, truncate_history, validate_llm_options
from app.core.config import Settings
from app.core.llm import LLMClient, build_chat_messages
from app.core.security import require_jwt_or_api_key
from app.core.websearch import search_duckduckgo_detailed

logger = logging.getLogger(__name__)
logger.info("routes_debug loaded")

router = APIRouter(prefix="/debug", tags=["debug"])

_ALLOWED_SETTING_OVERRIDES = {
    "llm_model_path",
    "llm_temperature",
    "llm_max_output_tokens",
    "llm_timeout_sec",
    "llm_context_tokens",
    "llm_n_gpu_layers",
    "llm_speculative_enabled",
    "llm_speculative_model_path",
    "llm_speculative_max_draft_tokens",
    "llm_speculative_context_tokens",
    "llm_speculative_n_gpu_layers",
    "chat_system_prompt",
}


async def _ensure_auth(request: Request) -> None:
    await require_jwt_or_api_key(request)


class HistoryEntry(BaseModel):
    role: Literal["user", "assistant", "system"] = "user"
    content: str


class ProfileDescriptor(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=160)
    settings: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    samples: int = Field(default=1, ge=1, le=5)


class LLMProfilesRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=6000)
    history: list[HistoryEntry] = Field(default_factory=list)
    profiles: list[ProfileDescriptor] = Field(..., min_length=1, max_length=8)


@router.get("/search")
async def debug_search(q: str, limit: int = 5, _: None = Depends(require_jwt_or_api_key)) -> dict:
    result = await search_duckduckgo_detailed(q, max_results=limit)
    return result



def _coerce_mode(value: str | None) -> str:
    if not value:
        return "standard"
    lowered = value.lower()
    if lowered not in {"standard", "speculative"}:
        raise HTTPException(status_code=400, detail="mode invalide")
    return lowered

@router.post("/llm-test")
async def debug_llm_test(
    request: Request,
    _: None = Depends(_ensure_auth),
) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"payload invalide: {exc}") from exc
    logger.debug("debug_llm_test payload received: %s", payload)
    raw_prompt = payload.get("prompt")
    prompt = raw_prompt.strip() if isinstance(raw_prompt, str) else None
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt manquant")
    raw_mode = payload.get("mode")
    mode = _coerce_mode(str(raw_mode) if raw_mode is not None else None)

    base_settings = Settings()
    system_prompt = getattr(base_settings, "chat_system_prompt", "Tu es IVY, assistant local.")
    messages = build_chat_messages(system=system_prompt, prompt=prompt.strip())

    update = {"llm_speculative_enabled": mode == "speculative"}
    settings = base_settings.model_copy(update=update)
    if mode == "speculative" and not settings.llm_speculative_model_path:
        raise HTTPException(status_code=400, detail="Modèle spéculatif non configuré")

    client = LLMClient(settings)
    started = time.perf_counter()
    try:
        response = await client.chat(messages)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc)})
    latency_ms = (time.perf_counter() - started) * 1000.0

    text = response.get("text", "")
    speculative = bool(response.get("speculative"))
    return {
        "mode": mode,
        "text": text.strip(),
        "latency_ms": latency_ms,
        "speculative": speculative,
}


def _sanitize_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in _ALLOWED_SETTING_OVERRIDES:
        if key in raw:
            value = raw[key]
            if key == "llm_speculative_enabled":
                sanitized[key] = bool(value)
                continue
            if key in {
                "llm_max_output_tokens",
                "llm_timeout_sec",
                "llm_context_tokens",
                "llm_n_gpu_layers",
                "llm_speculative_max_draft_tokens",
                "llm_speculative_context_tokens",
                "llm_speculative_n_gpu_layers",
            }:
                try:
                    coerced = int(value)
                except (TypeError, ValueError):
                    continue
                sanitized[key] = coerced
                continue
            if key == "llm_temperature":
                try:
                    sanitized[key] = float(value)
                except (TypeError, ValueError):
                    continue
                continue
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    sanitized[key] = cleaned
            else:
                sanitized[key] = value
    return sanitized


def _build_history(entries: Sequence[HistoryEntry]) -> list[tuple[str, str]]:
    trimmed: list[str] = []
    for entry in entries:
        content = entry.content.strip()
        if not content:
            continue
        trimmed.append(content)
    truncated_contents = truncate_history(trimmed)

    history: list[tuple[str, str]] = []
    idx = 0
    for entry in entries:
        content = entry.content.strip()
        if not content:
            continue
        if idx >= len(truncated_contents):
            break
        history.append((entry.role, truncated_contents[idx]))
        idx += 1
    return history


@router.post("/llm-profiles")
async def benchmark_llm_profiles(
    request: Request,
    _: None = Depends(_ensure_auth),
) -> dict[str, Any]:
    try:
        raw_payload = await request.json()
    except Exception as exc:  # pragma: no cover - depends on client
        raise HTTPException(status_code=400, detail=f"payload invalide: {exc}") from exc
    try:
        payload = LLMProfilesRequest.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    base_settings = Settings()
    history = _build_history(payload.history)
    prompt_value = payload.prompt.strip()
    results: list[dict[str, Any]] = []

    for descriptor in payload.profiles:
        overrides = _sanitize_overrides(descriptor.settings)
        applied_settings = base_settings.model_copy(update=overrides) if overrides else base_settings
        system_prompt = getattr(applied_settings, "chat_system_prompt", base_settings.chat_system_prompt)
        messages_template = build_chat_messages(
            system=system_prompt,
            history=history,
            prompt=prompt_value,
        )

        options = validate_llm_options(descriptor.options, applied_settings)
        temperature = float(options.get("temperature", applied_settings.llm_temperature))
        max_tokens = int(options.get("max_tokens", applied_settings.llm_max_output_tokens))
        extra_options = {k: v for k, v in options.items() if k not in {"temperature", "max_tokens"}}
        applied_options = dict(extra_options)
        applied_options["temperature"] = temperature
        applied_options["max_tokens"] = max_tokens

        profile_result: dict[str, Any] = {
            "name": descriptor.name,
            "description": descriptor.description,
            "applied_settings": overrides,
            "applied_options": applied_options,
            "samples": descriptor.samples,
            "runs": [],
            "errors": [],
        }

        client = LLMClient(applied_settings)
        for _ in range(descriptor.samples):
            messages = list(messages_template)
            start_time = time.perf_counter()
            try:
                response = await client.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_options=extra_options,
                )
            except HTTPException as exc:
                profile_result["errors"].append(f"[HTTP {exc.status_code}] {exc.detail}")
                continue
            except Exception as exc:  # pragma: no cover - runtime dependant
                profile_result["errors"].append(str(exc))
                continue

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            raw = response.get("raw") if isinstance(response, dict) else None
            usage = raw.get("usage") if isinstance(raw, dict) else None
            profile_result["runs"].append(
                {
                    "latency_ms": latency_ms,
                    "speculative": bool(response.get("speculative")) if isinstance(response, dict) else False,
                    "text": truncate_field(response.get("text", "").strip() if isinstance(response, dict) else ""),
                    "usage": usage,
                }
            )

        if profile_result["runs"]:
            avg = sum(run["latency_ms"] for run in profile_result["runs"]) / len(profile_result["runs"])
            profile_result["average_latency_ms"] = avg
        results.append(profile_result)

    return {"prompt": payload.prompt, "profiles": results}

    base_settings = Settings()
    history = _build_history(payload.history)

    prompt_value = payload.prompt.strip()
    results: list[dict[str, Any]] = []

    for descriptor in payload.profiles:
        overrides = _sanitize_overrides(descriptor.settings)
        applied_settings = base_settings.model_copy(update=overrides) if overrides else base_settings
        system_prompt = getattr(applied_settings, "chat_system_prompt", base_settings.chat_system_prompt)
        messages_template = build_chat_messages(
            system=system_prompt,
            history=history,
            prompt=prompt_value,
        )
        if descriptor.settings.get("chat_system_prompt") and "chat_system_prompt" not in overrides:
            # si prompt custom non autoris��, utiliser valeur nettoy��e
            overrides["chat_system_prompt"] = descriptor.settings["chat_system_prompt"]
            applied_settings = base_settings.model_copy(update=overrides)

        options = validate_llm_options(descriptor.options, applied_settings)
        temperature = float(options.get("temperature", applied_settings.llm_temperature))
        max_tokens = int(options.get("max_tokens", applied_settings.llm_max_output_tokens))
        extra_options = {k: v for k, v in options.items() if k not in {"temperature", "max_tokens"}}
        applied_options = dict(extra_options)
        applied_options["temperature"] = temperature
        applied_options["max_tokens"] = max_tokens

        profile_result: dict[str, Any] = {
            "name": descriptor.name,
            "description": descriptor.description,
            "applied_settings": overrides,
            "applied_options": applied_options,
            "samples": descriptor.samples,
            "runs": [],
            "errors": [],
        }

        client = LLMClient(applied_settings)
        for sample_idx in range(descriptor.samples):
            messages = list(messages_template)
            start_time = time.perf_counter()
            try:
                response = await client.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_options=extra_options,
                )
            except HTTPException as exc:
                profile_result["errors"].append(f"[HTTP {exc.status_code}] {exc.detail}")
                continue
            except Exception as exc:  # pragma: no cover - runtime dependant
                profile_result["errors"].append(str(exc))
                continue

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            raw = response.get("raw") if isinstance(response, dict) else None
            usage = raw.get("usage") if isinstance(raw, dict) else None
            profile_result["runs"].append(
                {
                    "latency_ms": latency_ms,
                    "speculative": bool(response.get("speculative")) if isinstance(response, dict) else False,
                    "text": truncate_field(response.get("text", "").strip() if isinstance(response, dict) else ""),
                    "usage": usage,
                }
            )

        if profile_result["runs"]:
            avg = sum(run["latency_ms"] for run in profile_result["runs"]) / len(profile_result["runs"])
            profile_result["average_latency_ms"] = avg
        results.append(profile_result)

    return {"prompt": payload.prompt, "profiles": results}
