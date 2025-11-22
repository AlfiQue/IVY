from __future__ import annotations

import time
from typing import Any

try:  # optional
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover
    Counter = None  # type: ignore
    Histogram = None  # type: ignore


REQ_COUNTER = Counter("ivy_http_requests_total", "HTTP requests", ["endpoint", "status"]) if Counter else None
REQ_LATENCY = Histogram("ivy_http_request_seconds", "HTTP request latency", ["endpoint"]) if Histogram else None
PLUGINS_EXEC = Counter("ivy_plugins_exec_total", "Plugins executions", ["name", "status"]) if Counter else None
LLM_TOKENS = Counter("ivy_llm_tokens_total", "LLM tokens streamed") if Counter else None
RATE_LIMITED = Counter("ivy_rate_limited_total", "Requests limited (429)") if Counter else None
AUTH_ERRORS = Counter("ivy_auth_errors_total", "Auth failures") if Counter else None


def record_request(endpoint: str, status: int, duration_s: float) -> None:
    if REQ_COUNTER:
        try:
            REQ_COUNTER.labels(endpoint=endpoint, status=str(status)).inc()
        except Exception:
            pass
    if REQ_LATENCY:
        try:
            REQ_LATENCY.labels(endpoint=endpoint).observe(duration_s)
        except Exception:
            pass


def inc_plugin_exec(name: str, status: str) -> None:
    if PLUGINS_EXEC:
        try:
            PLUGINS_EXEC.labels(name=name, status=status).inc()
        except Exception:
            pass


def inc_llm_tokens(n: int = 1) -> None:
    if LLM_TOKENS:
        try:
            LLM_TOKENS.inc(n)
        except Exception:
            pass


def inc_rate_limited() -> None:
    if RATE_LIMITED:
        try:
            RATE_LIMITED.inc(1)
        except Exception:
            pass


def inc_auth_error() -> None:
    if AUTH_ERRORS:
        try:
            AUTH_ERRORS.inc(1)
        except Exception:
            pass


async def metrics_middleware(request, call_next):  # type: ignore
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    try:
        record_request(request.url.path, response.status_code, duration)
    except Exception:
        pass
    return response
