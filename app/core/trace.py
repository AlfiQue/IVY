from __future__ import annotations

import uuid
from contextvars import ContextVar


_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    tid = str(uuid.uuid4())
    _trace_id.set(tid)
    return tid


def set_trace_id(tid: str | None) -> None:
    _trace_id.set(tid)


def get_trace_id() -> str | None:
    return _trace_id.get()

