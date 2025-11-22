from __future__ import annotations

from typing import Any, Dict


def error_response(code: str, message: str, *, details: Any | None = None, trace_id: str | None = None, status_code: int = 400) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    if trace_id is not None:
        payload["error"]["trace_id"] = trace_id
    return payload

