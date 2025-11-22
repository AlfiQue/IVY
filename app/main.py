from __future__ import annotations

from contextlib import asynccontextmanager
import io
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import (
    auth_router,
    backup_router,
    health_router,
    history_router,
    jobs_router,
    rag_router,
    sessions_router,
    metrics_router,
    config_router,
    apikeys_router,
    chat_router,
    llm_router,
    memory_router,
    debug_router,
    jeedom_router,
    plugins_router,
    voice_router,
    learning_router,
    commands_router,
)
from app.core.logger import get_logger
from app.core.rate_limit import rate_limit_middleware
from app.core.config import Settings
from app.core.security import attach_user_middleware, maybe_reset_admin
from app.core.rag import RAGEngine
from app.core.jobs import jobs_manager
from app.core import sessions as sessions_module, chat_store
from app.core.trace import new_trace_id, set_trace_id
from app.core.metrics import metrics_middleware

config = Settings()

@asynccontextmanager
async def _lifespan(app: FastAPI):
    await chat_store.init_db()
    yield

app = FastAPI(lifespan=_lifespan)

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
app.include_router(chat_router)
app.include_router(llm_router)
app.include_router(memory_router)
app.include_router(debug_router)
app.include_router(jeedom_router)
app.include_router(plugins_router)
app.include_router(voice_router)
app.include_router(learning_router)
app.include_router(commands_router)
app.include_router(history_router)
app.include_router(backup_router)
app.include_router(rag_router)
app.include_router(sessions_router)
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(metrics_router)
app.include_router(config_router)
app.include_router(apikeys_router)

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
        app.mount("/admin", StaticFiles(directory=str(_ui_dist), html=True), name="admin")
        assets_dir = _ui_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir), html=False), name="assets")
        @app.get("/sw.js")
        async def _sw_js():  # type: ignore[func-returns-value]
            path = _ui_dist / "sw.js"
            if path.exists():
                return FileResponse(str(path))
            return FileResponse(str(_ui_dist / "index.html"))

        @app.get("/manifest.webmanifest")
        async def _manifest():  # type: ignore[func-returns-value]
            path = _ui_dist / "manifest.webmanifest"
            if path.exists():
                return FileResponse(str(path), media_type="application/manifest+json")
            return FileResponse(str(_ui_dist / "index.html"))
        # Placeholder icons to avoid 404 if not present
        def _gen_png(size: int) -> bytes:
            try:
                from PIL import Image, ImageDraw, ImageFont  # type: ignore

                img = Image.new("RGBA", (size, size), (11, 11, 11, 255))
                draw = ImageDraw.Draw(img)
                # Draw a simple circle and text IVY
                r = size // 2 - size // 10
                draw.ellipse([(size//2 - r, size//2 - r), (size//2 + r, size//2 + r)], fill=(0, 200, 120, 255))
                txt = "IVY"
                try:
                    font = ImageFont.load_default()
                except Exception:
                    font = None
                tw, th = draw.textsize(txt, font=font) if font else (len(txt)*size//8, size//6)
                draw.text(((size - tw)//2, (size - th)//2), txt, fill=(0,0,0,255), font=font)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
            except Exception:
                # Minimal 1x1 PNG fallback
                return bytes.fromhex(
                    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000100ffff03000006000557bf2a0000000049454e44ae426082"
                )

        @app.get("/icon-192.png")
        async def _icon192():  # type: ignore[func-returns-value]
            p = _ui_dist / "icon-192.png"
            if p.exists():
                return FileResponse(str(p), media_type="image/png")
            data = _gen_png(192)
            return Response(content=data, media_type="image/png")

        @app.get("/icon-512.png")
        async def _icon512():  # type: ignore[func-returns-value]
            p = _ui_dist / "icon-512.png"
            if p.exists():
                return FileResponse(str(p), media_type="image/png")
            data = _gen_png(512)
            return Response(content=data, media_type="image/png")

        @app.get("/favicon.ico")
        async def _favicon():  # type: ignore[func-returns-value]
            p = _ui_dist / "favicon.ico"
            if p.exists():
                return FileResponse(str(p), media_type="image/x-icon")
            # generate ico from 32px png
            try:
                from PIL import Image  # type: ignore

                img_data = _gen_png(32)
                img = Image.open(io.BytesIO(img_data))
                buf = io.BytesIO()
                img.save(buf, format="ICO")
                return Response(content=buf.getvalue(), media_type="image/x-icon")
            except Exception:
                return Response(content=_gen_png(32), media_type="image/png")
        # Servir aussi la racine avec l'UI (fallback SPA)
        app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui-root")
        # Redirections pratiques vers l'UI
        @app.get("/")
        async def _root_redirect():  # type: ignore[func-returns-value]
            return RedirectResponse(url="/admin/")
        @app.get("/admin")
        async def _admin_redirect():  # type: ignore[func-returns-value]
            return RedirectResponse(url="/admin/")
        # Eviter 404 quand l'utilisateur ouvre /llm directement
        @app.get("/llm")
        async def _llm_redirect():  # type: ignore[func-returns-value]
            return RedirectResponse(url="/admin/llm")
except Exception:
    pass


async def _startup_logging() -> None:
    """Journalise le démarrage du serveur."""
    logger.info("Serveur démarré")

app.add_event_handler("startup", _startup_logging)


