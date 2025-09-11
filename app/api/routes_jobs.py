from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from app.core.jobs import jobs_manager
from app.core.security import csrf_protect, require_jwt
from app.core.errors import error_response

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs() -> dict:
    return {"jobs": jobs_manager.list_jobs()}


@router.post("/add", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def add_job(payload: dict) -> dict:
    job_type = payload.get("type")
    params = payload.get("params") or {}
    schedule = payload.get("schedule") or {}
    description = payload.get("description")
    tag = payload.get("tag")
    if job_type not in {"plugin", "llm", "backup"}:
        raise HTTPException(status_code=400, detail=error_response("IVY_4105", "invalid type", details=job_type))
    jid = jobs_manager.add_job(job_type, params, schedule, description=description, tag=tag)
    return {"id": jid}


@router.post("/{job_id}/run-now", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def run_now(job_id: str) -> dict:
    ok = jobs_manager.run_now(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail=error_response("IVY_4041", "job not found"))
    return {"status": "scheduled"}


@router.delete("/{job_id}", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def delete_job(job_id: str) -> dict:
    ok = jobs_manager.remove_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job introuvable")
    return {"status": "deleted"}


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    item = jobs_manager.get_job(job_id)
    if not item:
        raise HTTPException(status_code=404, detail=error_response("IVY_4041", "job not found"))
    return item


@router.post("/{job_id}/update", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def update_job(job_id: str, payload: dict) -> dict:
    ok = jobs_manager.update_job(
        job_id,
        params=payload.get("params"),
        schedule=payload.get("schedule"),
        description=payload.get("description"),
        tag=payload.get("tag"),
    )
    if not ok:
        raise HTTPException(status_code=404, detail=error_response("IVY_4041", "job not found"))
    return {"status": "updated"}


@router.post("/{job_id}/cancel", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def cancel_job(job_id: str) -> dict:
    status = jobs_manager.cancel_job(job_id)
    return {"status": status}
