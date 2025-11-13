from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from fastapi.responses import StreamingResponse

from app.core import config as config_module
from app.core.security import csrf_protect, require_jwt

router = APIRouter(prefix="/backup", tags=["backup"])

MAX_BACKUP_BYTES = 200 * 1024 * 1024  # 200 MiB
ALLOWED_TOPLEVEL = {"manifest.json", "config.json", "history.db", "faiss_index", "logs"}


def _tail_lines(path: Path, n: int = 200) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception:
        return ""



def _version() -> str:
    try:
        from importlib.metadata import version

        return version("ivy")
    except Exception:
        return "unknown"


@router.get("/export", dependencies=[Depends(require_jwt)])
def export_backup(include_logs: bool = False) -> StreamingResponse:
    settings = config_module.get_settings()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"version": _version()}, ensure_ascii=False))
        cfg = Path("config.json")
        if cfg.exists():
            zf.write(cfg, arcname="config.json")
        db = Path(settings.db_path)
        if db.exists():
            zf.write(db, arcname="history.db")
        idx = Path(settings.rag_index_dir)
        if idx.exists():
            for p in idx.glob("**/*"):
                if p.is_file():
                    zf.write(p, arcname=str(Path("faiss_index") / p.relative_to(idx)))
        logs_dir = Path("app/logs")
        if include_logs and logs_dir.exists():
            total_logs = 0
            for p in logs_dir.glob("**/*.jsonl"):
                rel = Path("logs") / p.relative_to(logs_dir)
                data = _tail_lines(p, 200)
                total_logs += len(data.encode("utf-8"))
                if total_logs > MAX_BACKUP_BYTES // 4:
                    break
                zf.writestr(str(rel), data)
    buf.seek(0)
    headers = {"Content-Disposition": "attachment; filename=ivy-backup.zip"}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)



def _safe_extract(zipf: zipfile.ZipFile, dest: Path) -> None:
    for member in zipf.infolist():
        target = dest / member.filename
        target_resolved = target.resolve()
        if not str(target_resolved).startswith(str(dest.resolve())):
            raise HTTPException(status_code=400, detail="Archive invalide")
        if member.is_dir():
            target_resolved.mkdir(parents=True, exist_ok=True)
        else:
            target_resolved.parent.mkdir(parents=True, exist_ok=True)
            with zipf.open(member) as src, open(target_resolved, "wb") as dst:
                dst.write(src.read())



def _validate_backup(zf: zipfile.ZipFile) -> None:
    total = 0
    for member in zf.infolist():
        total += member.file_size
        if total > MAX_BACKUP_BYTES:
            raise HTTPException(status_code=400, detail="Archive trop volumineuse")
        top = Path(member.filename).parts[0] if Path(member.filename).parts else ""
        if top and top not in ALLOWED_TOPLEVEL:
            raise HTTPException(status_code=400, detail=f"Fichier non autorise: {member.filename}")


@router.post("/import", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
async def import_backup(file: UploadFile = File(...), dry_run: bool = True, confirm: bool = False) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail={"error": {"code": "IVY_4000", "message": "zip required"}})
    data = await file.read()
    if len(data) > MAX_BACKUP_BYTES:
        raise HTTPException(status_code=413, detail="Archive trop volumineuse")
    settings = config_module.get_settings()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        _validate_backup(zf)
        names = zf.namelist()
        version = "unknown"
        if "manifest.json" in names:
            try:
                version = json.loads(zf.read("manifest.json").decode("utf-8")).get("version", "unknown")
            except Exception:
                version = "unknown"
        plan: list[dict[str, str]] = []
        if "config.json" in names:
            plan.append({"write": "config.json"})
        if "history.db" in names:
            plan.append({"write": settings.db_path})
        faiss_files = [n for n in names if n.startswith("faiss_index/")]
        for n in faiss_files:
            dest = str(Path(settings.rag_index_dir) / Path(n).relative_to("faiss_index"))
            plan.append({"write": dest})
        log_files = [n for n in names if n.startswith("logs/")]
        if not dry_run:
            if not confirm:
                raise HTTPException(status_code=400, detail={"error": {"code": "IVY_4001", "message": "confirmation requise"}})
            tmp = Path(".tmp_import")
            tmp.mkdir(exist_ok=True)
            try:
                _safe_extract(zf, tmp)
                if (tmp / "config.json").exists():
                    (tmp / "config.json").replace("config.json")
                if (tmp / "history.db").exists():
                    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
                    (tmp / "history.db").replace(settings.db_path)
                for n in faiss_files:
                    src = tmp / n
                    dest = Path(settings.rag_index_dir) / Path(n).relative_to("faiss_index")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    src.replace(dest)
                for n in log_files:
                    src = tmp / n
                    dest = Path("app/logs/imported") / Path(n).relative_to("logs")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    src.replace(dest)
            finally:
                for p in tmp.rglob("*"):
                    try:
                        if p.is_file():
                            p.unlink()
                    except Exception:
                        pass
                try:
                    tmp.rmdir()
                except Exception:
                    pass
        return {"version": version, "plan": plan, "dry_run": dry_run, "requires_confirm": not dry_run}
