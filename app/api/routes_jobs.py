from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import (
    BaseModel,
    Field,
    PositiveInt,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.core import job_prompts
from app.core import prompts as prompts_store
from app.core.errors import error_response
from app.core.history import search_events
from app.core.jobs import jobs_manager
from app.core.security import csrf_protect, require_jwt, require_jwt_or_api_key

router = APIRouter(prefix="/jobs", tags=["jobs"])


class ScheduleInput(BaseModel):
    trigger: Literal["immediate", "interval", "date", "cron"] = "immediate"
    every_minutes: Optional[PositiveInt] = Field(default=None, le=24 * 60)
    run_date: Optional[datetime] = None
    cron_hour: Optional[int] = Field(default=None, ge=0, le=23)
    cron_minute: Optional[int] = Field(default=None, ge=0, le=59)
    day_of_week: Optional[str] = None

    @model_validator(mode="after")
    def _validate(self) -> "ScheduleInput":
        trigger = self.trigger
        if trigger == "interval" and not self.every_minutes:
            raise ValueError("every_minutes requis pour les taches intervalle")
        if trigger == "date" and self.run_date is None:
            raise ValueError("run_date requis pour les taches de date")
        if trigger == "cron":
            if self.cron_hour is None:
                self.cron_hour = 3
            if self.cron_minute is None:
                self.cron_minute = 0
        return self


class JobRequest(BaseModel):
    type: Literal["llm", "backup", "rag", "plugin"]
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
            payload = {"prompt": prompt, "options": options}
            if value.get("system"):
                payload["system"] = value.get("system")
            return payload
        if job_type == "rag":
            return {"full": bool(value.get("full"))}
        if job_type == "plugin":
            name = value.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name requis pour les jobs plugin")
            plugin_params = value.get("params") or {}
            if not isinstance(plugin_params, dict):
                raise ValueError("params plugin doit etre un objet")
            return {"name": name, "params": plugin_params}
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


class PromptPayload(BaseModel):
    prompt: str
    favorite: bool = False


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


@router.get("")
async def list_jobs(
    job_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    _: None = Depends(_jobs_auth),
) -> dict:
    items = jobs_manager.list_jobs()
    if job_type:
        items = [item for item in items if str(item.get("type", "")).lower() == job_type.lower()]
    if status:
        items = [item for item in items if str(item.get("status", "")).lower() == status.lower()]
    if q:
        lookup = q.lower()
        items = [
            item
            for item in items
            if lookup in (str(item.get("description") or "")).lower()
            or lookup in (str(item.get("tag") or "")).lower()
            or lookup in (str(item.get("id") or "")).lower()
        ]
    return {"jobs": items}


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


@router.get("/prompts/recent", dependencies=[Depends(require_jwt)])
async def job_prompts_recent(limit: int = Query(10, ge=1, le=50)) -> dict:
    items = await prompts_store.list_recent(limit)
    return {"items": items}


@router.get("/prompts/favorites", dependencies=[Depends(require_jwt)])
async def job_prompts_favorites(limit: int = Query(10, ge=1, le=50)) -> dict:
    items = await prompts_store.list_top(limit)
    return {"items": items}


@router.get("/prompts/{kind}")
def list_prompt_entries(kind: Literal["recent", "favorites"], _: None = Depends(require_jwt)) -> dict:
    return {"items": job_prompts.list_prompts(kind)}


@router.post("/prompts/save", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def save_prompt_entry(payload: PromptPayload) -> dict:
    item = job_prompts.save_prompt(payload.prompt, favorite=payload.favorite)
    return {"item": item}


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


@router.post("/{job_id}/duplicate", dependencies=[Depends(require_jwt), Depends(csrf_protect)])
def duplicate_job(job_id: str, payload: dict | None = None) -> dict:
    base = jobs_manager.get_job(job_id)
    if not base:
        raise HTTPException(status_code=404, detail=error_response("IVY_4041", "job not found"))
    description = (payload or {}).get("description") or f"{base.get('description') or base.get('tag') or job_id} (copie)"
    tag = (payload or {}).get("tag") or base.get("tag")
    schedule = base.get("schedule") or {"trigger": "cron", "cron": {"hour": 3, "minute": 0}}
    new_id = jobs_manager.add_job(
        base["type"],
        base.get("params") or {},
        schedule,
        description=description,
        tag=tag,
    )
    return {"id": new_id}


@router.get("/{job_id}/runs")
async def job_runs(job_id: str, limit: int = Query(10, ge=1, le=50), _: None = Depends(_jobs_auth)) -> dict:
    items = jobs_manager.get_recent_runs(job_id, limit=limit)
    if len(items) < limit:
        history = await search_events(limit=limit, job_id=job_id, event_type="job.run")
        hist_items = []
        for entry in history.get("items", []):
            payload = entry.get("payload") or {}
            hist_items.append(
                {
                    "status": payload.get("status") or entry.get("status"),
                    "timestamp": entry.get("created_at"),
                    "detail": payload.get("detail"),
                }
            )
        items.extend(hist_items)
    if not items and not jobs_manager.get_job(job_id):
        raise HTTPException(status_code=404, detail=error_response("IVY_4041", "job not found"))
    return {"items": items[:limit]}
