from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _format_message(
    msg_type: str,
    req_id: str,
    source: str,
    event: str,
    payload: Any,
) -> str:
    """Formate un message JSON normalisé."""
    return json.dumps(
        {
            "type": msg_type,
            "req_id": req_id,
            "source": source,
            "event": event,
            "payload": payload,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
    )


def send_token(req_id: str, source: str, token: str) -> str:
    """Construit un message pour un token de génération."""
    return _format_message("event", req_id, source, "token", token)


def send_status(req_id: str, source: str, status: str) -> str:
    """Construit un message de statut."""
    return _format_message("event", req_id, source, "status", status)


def send_error(req_id: str, source: str, error: str) -> str:
    """Construit un message d'erreur."""
    return _format_message("error", req_id, source, "error", error)


def send_end(req_id: str, source: str) -> str:
    """Construit un message de fin de flux."""
    return _format_message("event", req_id, source, "end", None)
