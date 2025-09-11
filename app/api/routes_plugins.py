from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File

from app.core import plugins
from app.core.security import csrf_protect, require_jwt
from app.core.errors import error_response

router = APIRouter(prefix="/plugins", tags=["plugins"])


def _ensure(name: str) -> None:
    if name not in plugins.REGISTRY:
        raise HTTPException(status_code=404, detail=error_response("IVY_4040", "plugin not found"))


@router.get("")
def list_plugins() -> dict[str, list[dict[str, object]]]:
    """Retourner les plugins et leurs métadonnées."""
    plugins.load_plugins()
    items = [
        {"name": n, "state": d["state"], "meta": d["meta"]}
        for n, d in plugins.REGISTRY.items()
    ]
    return {"plugins": items}


@router.post("/upload", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
async def upload_plugin(file: UploadFile = File(...)) -> dict[str, str]:
    """Upload et installation d'un plugin ZIP."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail=error_response("IVY_4000", "zip required"))
    data = await file.read()
    try:
        name = plugins.install_zip(data)
    except Exception as exc:  # pragma: no cover - cas d'erreurs de zip
        raise HTTPException(status_code=400, detail=error_response("IVY_4002", "install failed", details=str(exc))) from exc
    return {"message": f"Plugin {name} installe", "name": name}


@router.post("/{name}/enable", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def enable_plugin(name: str) -> dict[str, str]:
    _ensure(name)
    plugins.enable(name)
    return {"message": f"Plugin {name} activé"}


@router.post("/{name}/disable", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def disable_plugin(name: str) -> dict[str, str]:
    _ensure(name)
    plugins.disable(name)
    return {"message": f"Plugin {name} désactivé"}


@router.post("/{name}/start", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def start_plugin(name: str) -> dict[str, str]:
    _ensure(name)
    plugins.start(name)
    return {"message": f"Plugin {name} démarré"}


@router.post("/{name}/stop", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def stop_plugin(name: str) -> dict[str, str]:
    _ensure(name)
    plugins.stop(name)
    return {"message": f"Plugin {name} arrêté"}


@router.post("/{name}/reload", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def reload_plugin(name: str) -> dict[str, str]:
    _ensure(name)
    plugins.reload(name)
    return {"message": f"Plugin {name} rechargé"}


@router.delete("/{name}", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def delete_plugin(name: str) -> dict[str, str]:
    _ensure(name)
    plugins.delete(name)
    return {"message": f"Plugin {name} supprimé"}
