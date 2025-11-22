from __future__ import annotations

from .routes_auth import router as auth_router
from .routes_backup import router as backup_router
from .routes_health import router as health_router
from .routes_history import router as history_router
from .routes_jobs import router as jobs_router
from .routes_llm import router as llm_router
from .routes_rag import router as rag_router
from .routes_sessions import router as sessions_router
from .routes_metrics import router as metrics_router
from .routes_config import router as config_router
from .routes_apikeys import router as apikeys_router
from .routes_chat import router as chat_router
from .routes_memory import router as memory_router
from .routes_debug import router as debug_router
from .routes_jeedom import router as jeedom_router
from .routes_plugins import router as plugins_router
from .routes_voice import router as voice_router
from .routes_learning import router as learning_router
from .routes_commands import router as commands_router

__all__ = [
    "health_router",
    "chat_router",
    "memory_router",
    "debug_router",
    "jeedom_router",
    "plugins_router",
    "voice_router",
    "history_router",
    "backup_router",
    "rag_router",
    "sessions_router",
    "auth_router",
    "jobs_router",
    "metrics_router",
    "config_router",
    "apikeys_router",
    "llm_router",
    "learning_router",
    "commands_router",
]
