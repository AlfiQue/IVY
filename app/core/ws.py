from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from app.core.trace import get_trace_id


async def stream(
    websocket: WebSocket, prompt: str, options: dict[str, Any] | None = None
) -> None:
    """Diffuse les tokens générés pour ``prompt`` en temps réel."""
    await websocket.accept()
    try:
        import os

        from .llm import (  # import local pour éviter une dépendance coûteuse au chargement
            LLM,
        )

        model_path = os.environ.get("LLM_MODEL_PATH")
        if model_path is None:
            # Impossible de générer sans modèle ; on coupe la connexion.
            await websocket.close(code=1011)
            return

        llm = LLM(model_path)
        async for token in llm.astream(prompt, options):
            await websocket.send_text(token)
    finally:
        await websocket.close()


def serialize_event(
    req_id: str | None, source: str, event: str, payload: Any
) -> dict[str, Any]:
    """Sérialise un événement WebSocket au format commun."""
    return {
        "type": "event",
        "req_id": req_id,
        "source": source,
        "event": event,
        "payload": payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def send_event(
    websocket: WebSocket,
    req_id: str | None,
    source: str,
    event: str,
    payload: Any,
) -> None:
    """Envoie un événement générique sur la connexion WebSocket."""
    await websocket.send_json(serialize_event(req_id, source, event, payload))


async def send_token(
    websocket: WebSocket, req_id: str | None, source: str, token: str
) -> None:
    """Envoie un jeton généré."""
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
    await websocket.send_json(
        {
            "type": "error",
            "req_id": req_id,
            "source": source,
            "code": code or "IVY_4000",
            "message": error,
            "trace_id": get_trace_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            **({"details": details} if details is not None else {}),
        }
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
    await websocket.close(code=code)
