from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState
from app.core.llm import LLMClient, build_chat_messages
from app.core.trace import get_trace_id


async def stream(
    websocket: WebSocket, prompt: str, options: dict[str, Any] | None = None
) -> None:
    """Diffuse une reponse LLM via WebSocket."""
    await websocket.accept()
    req_id = None
    source = "llm"
    try:
        opts = dict(options or {})
        temperature = opts.pop("temperature", None)
        max_tokens = opts.pop("max_tokens", None)
        system_prompt = opts.pop("system", None)
        raw_history = opts.pop("history", None)

        history: list[tuple[str, str]] | None = None
        if isinstance(raw_history, list):
            history_items: list[tuple[str, str]] = []
            for item in raw_history:
                if isinstance(item, dict):
                    role = str(item.get("role", "user"))
                    content = str(item.get("content", ""))
                    history_items.append((role, content))
                elif isinstance(item, (tuple, list)) and len(item) >= 2:
                    history_items.append((str(item[0]), str(item[1])))
            history = history_items or None

        messages = build_chat_messages(system=system_prompt, history=history, prompt=prompt)
        client = LLMClient()
        result = await client.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_options=opts or None,
        )
        text = result.get("text", "")
        provider = result.get("provider", source)
        if text:
            await send_token(websocket, req_id, provider, text)
        await close_connection(websocket, req_id, provider)
    except Exception as exc:  # pragma: no cover - WebSocket runtime path
        await send_error(
            websocket,
            req_id,
            source,
            str(exc),
            code="IVY_WS_LLM_ERROR",
        )
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass

def serialize_event(
    req_id: str | None, source: str, event: str, payload: Any
) -> dict[str, Any]:
    """SÃ©rialise un Ã©vÃ©nement WebSocket au format commun."""
    return {
        "type": "event",
        "req_id": req_id,
        "source": source,
        "event": event,
        "payload": payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def _send_json_safe(websocket: WebSocket, data: dict[str, Any]) -> None:
    state = getattr(websocket, 'application_state', None)
    if state is not None and state is not WebSocketState.CONNECTED:
        return
    try:
        await websocket.send_json(data)
    except RuntimeError:
        pass

async def send_event(
    websocket: WebSocket,
    req_id: str | None,
    source: str,
    event: str,
    payload: Any,
) -> None:
    """Envoie un Ã©vÃ©nement gÃ©nÃ©rique sur la connexion WebSocket."""
    await _send_json_safe(websocket, serialize_event(req_id, source, event, payload))


async def send_token(
    websocket: WebSocket, req_id: str | None, source: str, token: str
) -> None:
    """Envoie un jeton gÃ©nÃ©rÃ©."""
    await send_event(websocket, req_id, source, "token", token)


async def send_error(
    websocket: WebSocket,
    req_id: str | None,
    source: str,
    error: str,
    code: str | None = None,
    details: object | None = None,
) -> None:
    """Envoie un message d'erreur (schéma classique + trace_id)."""
    await _send_json_safe(
        websocket,
        {
            "type": "error",
            "req_id": req_id,
            "source": source,
            "code": code or "IVY_4000",
            "message": error,
            "trace_id": get_trace_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            **({"details": details} if details is not None else {}),
        },
    )

async def send_status(
    websocket: WebSocket, req_id: str | None, source: str, status: Any
) -> None:
    """Envoie un message de statut."""
    await send_event(websocket, req_id, source, "status", status)


async def close_connection(
    websocket: WebSocket,
    req_id: str | None,
    source: str,
    code: int = 1000,
) -> None:
    """Envoie l'événement de fin puis ferme la connexion."""
    await send_event(websocket, req_id, source, "end", None)
    try:
        await websocket.close(code=code)
    except RuntimeError:
        pass


