from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.core.config import get_settings
from app.core.history import ping_db
from app.core.security import require_jwt_or_api_key

router = APIRouter(prefix="/health", tags=["health"])

FAISS_DIR = Path("app/data/faiss_index")
PLUGINS_DIR = Path("plugins")


async def _health_auth(request: Request):
    settings = get_settings()
    if getattr(settings, "health_requires_auth", False):
        await require_jwt_or_api_key(request, scopes=["health"])


@router.get("", dependencies=[Depends(_health_auth)])
async def get_health() -> dict[str, object]:
    """Retourne l'état de santé de l'application."""
    try:
        pkg_version = version("ivy")
    except PackageNotFoundError:  # pragma: no cover - dépend de l'installation
        pkg_version = "unknown"

    now = datetime.now(timezone.utc).isoformat()

    gpu_available = False
    try:  # pragma: no cover - l'absence de GPU est la norme en CI
        import torch  # type: ignore[import-not-found]

        gpu_available = torch.cuda.is_available()
    except Exception:
        gpu_available = False

    if PLUGINS_DIR.exists():
        plugins_count = sum(1 for p in PLUGINS_DIR.iterdir() if p.is_dir())
    else:
        plugins_count = 0

    db_ok = await ping_db()
    faiss_ok = FAISS_DIR.exists()

    status = "ok" if db_ok and faiss_ok else "error"

    return {
        "status": status,
        "version": pkg_version,
        "time": now,
        "gpu": gpu_available,
        "plugins_count": plugins_count,
        "db_ok": db_ok,
        "faiss_ok": faiss_ok,
    }
