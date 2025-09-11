from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException


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


def raise_http_error(code: str, message: str, *, status_code: int = 400, details: Any | None = None) -> None:
    raise HTTPException(status_code=status_code, detail=error_response(code, message, details=details))

