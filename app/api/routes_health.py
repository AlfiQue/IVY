from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import APIRouter

from app.core.history import ping_db
from app.core import chat_store

router = APIRouter(prefix="/health", tags=["health"])

FAISS_DIR = Path("app/data/faiss_index")


@router.get("")
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

    db_ok = await ping_db()
    conversations_total = await chat_store.count_conversations()
    qa_total = await chat_store.count_qa()

    faiss_ok = FAISS_DIR.exists()

    # Système: charge CPU/Mémoire (optionnel)
    cpu_percent: float | None = None
    mem_percent: float | None = None
    mem_total: int | None = None
    mem_available: int | None = None
    try:  # pragma: no cover - dépend de l'env
        import psutil  # type: ignore

        cpu_percent = float(psutil.cpu_percent(interval=0.1))
        vm = psutil.virtual_memory()
        mem_percent = float(vm.percent)
        mem_total = int(vm.total)
        mem_available = int(vm.available)
    except Exception:
        pass

    status = "ok" if db_ok and faiss_ok else "error"

    return {
        "status": status,
        "version": pkg_version,
        "time": now,
        "gpu": gpu_available,
        "conversations_total": conversations_total,
        "qa_total": qa_total,
        "db_ok": db_ok,
        "faiss_ok": faiss_ok,
        "cpu_percent": cpu_percent,
        "mem_percent": mem_percent,
        "mem_total": mem_total,
        "mem_available": mem_available,
    }
