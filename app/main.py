from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api import (
    auth_router,
    backup_router,
    health_router,
    history_router,
    jobs_router,
    llm_router,
    plugins_router,
    rag_router,
    sessions_router,
    metrics_router,
)
from app.core.logger import get_logger
from app.core.rate_limit import rate_limit_middleware
from app.core.config import Settings
from app.core.security import attach_user_middleware, maybe_reset_admin
from app.core.rag import RAGEngine
from app.core.jobs import jobs_manager
from app.core import sessions as sessions_module
from app.core.trace import new_trace_id, set_trace_id
from app.core.metrics import metrics_middleware

config = Settings()

app = FastAPI()

# Initialiser le logger serveur
logger = get_logger("server")
app.add_event_handler("startup", maybe_reset_admin)

app.middleware("http")(rate_limit_middleware(config.rate_limit_rps))
app.middleware("http")(attach_user_middleware())
if config.enable_metrics:
    app.middleware("http")(metrics_middleware)


@app.middleware("http")
async def _session_touch_middleware(request, call_next):
    # Trace ID
    tid = request.headers.get("X-Trace-Id") or new_trace_id()
    set_trace_id(tid)
    sid = request.cookies.get("session_id")
    if sid:
        try:
            sessions_module.touch(sid)
        except Exception:
            pass
    response = await call_next(request)
    try:
        response.headers["X-Trace-Id"] = tid
    except Exception:
        pass
    return response

# Ajuster credentials si origines wildcard
_allow_credentials = config.cors_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(plugins_router)
app.include_router(llm_router)
app.include_router(history_router)
app.include_router(backup_router)
app.include_router(rag_router)
app.include_router(sessions_router)
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(metrics_router)

# Scheduler des jobs (startup/shutdown)
app.add_event_handler("startup", jobs_manager.start)
app.add_event_handler("shutdown", jobs_manager.shutdown)

# Initialiser RAG (watchers + planification)
_rag_engine = RAGEngine(config)
if getattr(config, "rag_watchers_enabled", True):
    app.add_event_handler("startup", _rag_engine.start_watchers)
    app.add_event_handler("shutdown", _rag_engine.stop_watchers)
if getattr(config, "rag_reindex_enabled", True):
    app.add_event_handler(
        "startup", lambda: _rag_engine.start_scheduler(config.rag_reindex_interval_minutes)
    )
    app.add_event_handler("shutdown", _rag_engine.stop_scheduler)

# Mise à jour desktop: servir statiquement updates/desktop/
try:
    app.mount("/updates/desktop", StaticFiles(directory="updates/desktop", html=False), name="updates-desktop")
except Exception:
    pass


# Servir l'UI statique buildée (webui/dist) sous /ui si présente, pour unifier sur le port 8000
try:
    _ui_dist = Path("webui") / "dist"
    if _ui_dist.exists():
        app.mount("/ui", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
except Exception:
    pass


@app.on_event("startup")
async def _startup_logging() -> None:
    """Journalise le démarrage du serveur."""
    logger.info("Serveur démarré")
