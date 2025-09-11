from __future__ import annotations

from .routes_auth import router as auth_router
from .routes_backup import router as backup_router
from .routes_health import router as health_router
from .routes_history import router as history_router
from .routes_jobs import router as jobs_router
from .routes_llm import router as llm_router
from .routes_plugins import router as plugins_router
from .routes_rag import router as rag_router
from .routes_sessions import router as sessions_router
from .routes_metrics import router as metrics_router

__all__ = [
    "health_router",
    "plugins_router",
    "llm_router",
    "history_router",
    "backup_router",
    "rag_router",
    "sessions_router",
    "auth_router",
    "jobs_router",
    "metrics_router",
]
