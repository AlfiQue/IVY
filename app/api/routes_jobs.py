from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    PositiveInt,
    field_validator,
    model_validator,
)

from app.core.errors import error_response
from app.core.jobs import jobs_manager
from app.core.security import csrf_protect, require_jwt, require_jwt_or_api_key


class ScheduleInput(BaseModel):
    trigger: Literal["immediate", "interval", "date", "cron"] = "immediate"
    every_minutes: Optional[PositiveInt] = Field(default=None, le=24 * 60)
    run_date: Optional[datetime] = None
    cron_hour: Optional[int] = Field(default=None, ge=0, le=23)
    cron_minute: Optional[int] = Field(default=None, ge=0, le=59)
    day_of_week: Optional[str] = None

    @model_validator(mode="after")
    def _validate(cls, values: "ScheduleInput") -> "ScheduleInput":
        trigger = values.trigger
        if trigger == "interval" and not values.every_minutes:
            raise ValueError("every_minutes requis pour les taches intervalle")
        if trigger == "date" and values.run_date is None:
            raise ValueError("run_date requis pour les taches de date")
        if trigger == "cron":
            if values.cron_hour is None:
                values.cron_hour = 3
            if values.cron_minute is None:
                values.cron_minute = 0
        return values


class JobRequest(BaseModel):
    type: Literal["llm", "backup"]
    params: Dict[str, Any] = Field(default_factory=dict)
    schedule: Optional[ScheduleInput] = None
    description: Optional[str] = None
    tag: Optional[str] = None

    @field_validator("params", mode="after")
    def _validate_params(cls, value: Dict[str, Any], info: ValidationInfo) -> Dict[str, Any]:
        job_type = info.data.get("type")
        if not isinstance(value, dict):
            raise ValueError("params doit etre un objet JSON")
        if job_type == "llm":
            prompt = value.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError("prompt requis pour les jobs LLM")
            options = value.get("options") or {}
            if not isinstance(options, dict):
                raise ValueError("options doit etre un objet")
            return {"prompt": prompt, "options": options}
        return value


class JobUpdatePayload(BaseModel):
    params: Optional[Dict[str, Any]] = None
    schedule: Optional[ScheduleInput] = None
    description: Optional[str] = None
    tag: Optional[str] = None

    @field_validator("params", mode="after")
    def _validate_params(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if value is not None and not isinstance(value, dict):
            raise ValueError("params doit etre un objet JSON")
        return value


def _normalize_schedule(schedule: Optional[ScheduleInput]) -> Dict[str, Any]:
    if schedule is None or schedule.trigger == "immediate":
        run_at = datetime.utcnow() + timedelta(seconds=1)
        return {"trigger": "date", "date": {"run_date": run_at.isoformat()}}
    if schedule.trigger == "interval":
        return {"trigger": "interval", "interval": {"minutes": schedule.every_minutes}}
    if schedule.trigger == "date":
        run_date = schedule.run_date or (datetime.utcnow() + timedelta(seconds=1))
        return {"trigger": "date", "date": {"run_date": run_date.isoformat()}}
    cron = {"minute": schedule.cron_minute or 0, "hour": schedule.cron_hour or 3}
    if schedule.day_of_week:
        cron["day_of_week"] = schedule.day_of_week
    return {"trigger": "cron", "cron": cron}


async def _jobs_auth(request: Request):
    return await require_jwt_or_api_key(request, scopes=["jobs"])


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(_: None = Depends(_jobs_auth)) -> dict:
    return {"jobs": jobs_manager.list_jobs()}


@router.post("/add", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def add_job(payload: JobRequest) -> dict:
    schedule = _normalize_schedule(payload.schedule)
    jid = jobs_manager.add_job(
        payload.type,
        payload.params,
        schedule,
        description=payload.description,
        tag=payload.tag,
    )
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
async def get_job(job_id: str, _: None = Depends(_jobs_auth)) -> dict:
    item = jobs_manager.get_job(job_id)
    if not item:
        raise HTTPException(status_code=404, detail=error_response("IVY_4041", "job not found"))
    return item


@router.post("/{job_id}/update", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def update_job(job_id: str, payload: JobUpdatePayload) -> dict:
    schedule = _normalize_schedule(payload.schedule) if payload.schedule is not None else None
    ok = jobs_manager.update_job(
        job_id,
        params=payload.params,
        schedule=schedule,
        description=payload.description,
        tag=payload.tag,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=error_response("IVY_4041", "job not found"))
    return {"status": "updated"}


@router.post("/{job_id}/cancel", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def cancel_job(job_id: str) -> dict:
    status = jobs_manager.cancel_job(job_id)
    return {"status": status}


@router.get("/{job_id}/runs")
async def job_runs(job_id: str, limit: int = Query(10, ge=1, le=50), _: None = Depends(_jobs_auth)) -> dict:
    items = jobs_manager.get_recent_runs(job_id, limit=limit)
    if not items and not jobs_manager.get_job(job_id):
        raise HTTPException(status_code=404, detail=error_response("IVY_4041", "job not found"))
    return {"items": items}
