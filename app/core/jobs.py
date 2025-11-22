from __future__ import annotations

import io
import json
import shutil
import zipfile
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings, get_settings
from app.core.logger import get_logger
from app.core import plugins as plugins_module
from app.core import prompts as prompts_store
from app.core.history import log_event_sync
from app.core.llm import LLM


logger = get_logger("server")


RETRY_DELAYS = [5, 15, 45]  # seconds
RECENT_RUNS_LIMIT = 20


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def _log_job_event(action: str, meta: "JobMeta | None", **extra: Any) -> None:
    payload: Dict[str, Any] = {"action": action}
    if meta:
        payload.update(
            {
                "job_id": meta.id,
                "type": meta.type,
                "status": meta.status,
                "attempts": meta.attempts,
                "success_count": getattr(meta, "success_count", 0),
                "failure_count": getattr(meta, "failure_count", 0),
                "description": meta.description,
                "tag": meta.tag,
                "last_error_at": getattr(meta, "last_error_at", None),
            }
        )
        if meta.params:
            payload["params"] = _json_safe(meta.params)
        if meta.schedule:
            payload["schedule"] = _json_safe(meta.schedule)
        if meta.last_error:
            payload["last_error"] = meta.last_error
    for key, value in extra.items():
        if value is None:
            continue
        payload[key] = _json_safe(value)
    try:
        log_event_sync(f"job.{action}", payload)
    except Exception:
        pass


@dataclass
class JobMeta:
    id: str
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    schedule: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    status: str = "PENDING"  # PENDING | RUNNING | SUCCESS | FAILED | RETRYING
    last_error: Optional[str] = None
    last_run: Optional[str] = None
    description: Optional[str] = None
    tag: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0
    last_error_at: Optional[str] = None
    recent_runs: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=RECENT_RUNS_LIMIT))


class JobsManager:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.scheduler = BackgroundScheduler(daemon=True)
        self.jobs: Dict[str, JobMeta] = {}
        self._cancel_flags: Dict[str, bool] = {}
        self._running: Dict[str, bool] = {}

    def _record_run(self, meta: JobMeta, status: str, detail: Optional[str] = None) -> None:
        entry = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "detail": detail,
            "attempts": meta.attempts,
        }
        try:
            meta.recent_runs.appendleft(entry)
        except Exception:
            pass

    # lifecycle
    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    # actions
    def _run_plugin(self, name: str, params: Dict[str, Any]) -> None:
        plugins_module.load_plugins()
        plugins_module.enable(name)
        plugins_module.start(name)
        plugins_module.run(name, **params)

    def _run_llm(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        if prompt:
            prompts_store.record_prompt_sync(prompt)
        llm = LLM()
        return llm.infer(prompt, options)

    def _run_rag(self, params: Dict[str, Any]) -> int:
        from app.core.rag import RAGEngine

        engine = RAGEngine(self.settings)
        full = bool(params.get("full", False))
        return engine.reindex(full=full)

    def _export_backup(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = Path("app/data/backups")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_zip = out_dir / f"backup-{ts}.zip"
        db_path = Path(self.settings.db_path)
        meta_path = Path(self.settings.rag_index_dir) / "meta.json"
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if db_path.exists():
                zf.write(db_path, arcname="history.db")
            if meta_path.exists():
                zf.write(meta_path, arcname="rag-meta.json")
        return out_zip


    def _job_wrapper(self, job_id: str) -> None:
        meta = self.jobs.get(job_id)
        if not meta:
            return
        if self._cancel_flags.get(job_id):
            meta.status = "CANCELLED"
            meta.last_run = datetime.now().isoformat()
            _log_job_event("cancelled", meta, reason="pre_run")
            self._record_run(meta, "CANCELLED", detail="pre_run")
            self._cancel_flags.pop(job_id, None)
            return
        self._running[job_id] = True
        meta.status = "RUNNING"
        meta.last_run = datetime.now().isoformat()
        _log_job_event("started", meta)
        self._record_run(meta, "RUNNING")
        try:
            if meta.type == "plugin":
                if self._cancel_flags.get(job_id):
                    meta.status = "CANCELLED"
                    _log_job_event("cancelled", meta, reason="plugin")
                    return
                self._run_plugin(meta.params.get("name", ""), meta.params.get("params", {}))
            elif meta.type == "llm":
                prompt = meta.params.get("prompt", "")
                options = meta.params.get("options")
                if self._cancel_flags.get(job_id):
                    meta.status = "CANCELLED"
                    _log_job_event("cancelled", meta, reason="llm")
                    return
                _ = self._run_llm(prompt, options)
            elif meta.type == "backup":
                path = self._export_backup()
                logger.info("Backup exporte: %s", path)
            elif meta.type == "rag":
                added = self._run_rag(meta.params or {})
                logger.info(
                    "RAG reindex (full=%s) -> %s chunks",
                    bool((meta.params or {}).get('full', False)),
                    added,
                )
            else:
                raise ValueError(f"type de job inconnu: {meta.type}")
            meta.status = "SUCCESS"
            meta.attempts = 0
            meta.last_error = None
            meta.last_error_at = None
            meta.success_count += 1
            _log_job_event("completed", meta)
            self._record_run(meta, "SUCCESS")
        except Exception as exc:
            meta.attempts += 1
            meta.last_error = str(exc)
            meta.failure_count += 1
            meta.last_error_at = datetime.now().isoformat()
            if meta.attempts <= len(RETRY_DELAYS):
                delay = RETRY_DELAYS[meta.attempts - 1]
                meta.status = "RETRYING"
                run_at = datetime.now() + timedelta(seconds=delay)
                if delay == 0:
                    self._job_wrapper(job_id)
                else:
                    self.scheduler.add_job(self._job_wrapper, DateTrigger(run_date=run_at), args=[job_id])
                _log_job_event("failed", meta, retry_in_seconds=delay, will_retry=True)
                logger.info("Job %s echec, retry dans %ss: %s", job_id, delay, exc)
                self._record_run(meta, "RETRYING", detail=str(exc))
            else:
                meta.status = "FAILED"
                _log_job_event("failed", meta, will_retry=False)
                logger.info("Job %s FAILED apres retries: %s", job_id, exc)
                self._record_run(meta, "FAILED", detail=str(exc))
        finally:
            self._running.pop(job_id, None)
            self._cancel_flags.pop(job_id, None)

    def _build_trigger(self, schedule: Dict[str, Any]):
        trig = (schedule or {}).get("trigger", "cron")
        if trig == "interval":
            kwargs = schedule.get("interval", {})
            return IntervalTrigger(**kwargs)
        if trig == "date":
            kwargs = schedule.get("date", {})
            run_date = kwargs.get("run_date")
            # accepter ISO string
            if isinstance(run_date, str):
                run_date = datetime.fromisoformat(run_date)
            return DateTrigger(run_date=run_date or (datetime.now() + timedelta(seconds=1)))
        # dÃ©faut: cron 03:00
        kwargs = schedule.get("cron", {})
        hour = kwargs.get("hour", 3)
        minute = kwargs.get("minute", 0)
        return CronTrigger(hour=hour, minute=minute)

    # public API
    def add_job(
        self,
        job_type: str,
        params: Dict[str, Any],
        schedule: Optional[Dict[str, Any]] = None,
        *,
        description: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> str:
        job_id = uuid4().hex[:12]
        meta = JobMeta(
            id=job_id,
            type=job_type,
            params=params,
            schedule=schedule or {},
            description=description,
            tag=tag,
        )
        self.jobs[job_id] = meta
        trigger = self._build_trigger(meta.schedule)
        self.scheduler.add_job(self._job_wrapper, trigger, args=[job_id], id=job_id, replace_existing=True)
        _log_job_event("scheduled", meta)
        return job_id

    def remove_job(self, job_id: str) -> bool:
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass
        meta = self.jobs.pop(job_id, None)
        if meta:
            _log_job_event("removed", meta)
        return meta is not None



    def list_jobs(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for job in self.scheduler.get_jobs():
            meta = self.jobs.get(job.id)
            items.append(
                {
                    "id": job.id,
                    "type": meta.type if meta else None,
                    "status": meta.status if meta else None,
                    "attempts": meta.attempts if meta else None,
                    "success_count": meta.success_count if meta else None,
                    "failure_count": meta.failure_count if meta else None,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "last_run": meta.last_run if meta else None,
                    "last_error": meta.last_error if meta else None,
                    "last_error_at": meta.last_error_at if meta else None,
                    "description": meta.description if meta else None,
                    "tag": meta.tag if meta else None,
                    "params": meta.params if meta else None,
                    "schedule": meta.schedule if meta else None,
                }
            )
        for jid, meta in self.jobs.items():
            if not any(x["id"] == jid for x in items):
                items.append(
                    {
                        "id": jid,
                        "type": meta.type,
                        "status": meta.status,
                        "attempts": meta.attempts,
                        "success_count": meta.success_count,
                        "failure_count": meta.failure_count,
                        "next_run": None,
                        "last_run": meta.last_run,
                        "last_error": meta.last_error,
                        "last_error_at": meta.last_error_at,
                        "description": meta.description,
                        "tag": meta.tag,
                        "params": meta.params,
                        "schedule": meta.schedule,
                    }
                )
        return items

    def run_now(self, job_id: str) -> bool:
        if job_id not in self.jobs:
            return False
        # planifie une execution immediate
        self.scheduler.add_job(self._job_wrapper, DateTrigger(run_date=datetime.now()), args=[job_id])
        return True

    def update_job(
        self,
        job_id: str,
        *,
        params: Dict[str, Any] | None = None,
        schedule: Dict[str, Any] | None = None,
        description: Optional[str] | None = None,
        tag: Optional[str] | None = None,
    ) -> bool:
        meta = self.jobs.get(job_id)
        if not meta:
            return False
        if params is not None:
            meta.params = params
        if schedule is not None:
            meta.schedule = schedule
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass
            trigger = self._build_trigger(meta.schedule)
            self.scheduler.add_job(self._job_wrapper, trigger, args=[job_id], id=job_id, replace_existing=True)
        if description is not None:
            meta.description = description
        if tag is not None:
            meta.tag = tag
        _log_job_event("updated", meta)
        return True

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        meta = self.jobs.get(job_id)
        if not meta:
            return None
        next_run = None
        try:
            job = next(j for j in self.scheduler.get_jobs() if j.id == job_id)
            if job.next_run_time:
                next_run = job.next_run_time.isoformat()
        except Exception:
            next_run = None
        return {
            "id": meta.id,
            "type": meta.type,
            "params": meta.params,
            "schedule": meta.schedule,
            "status": meta.status,
            "attempts": meta.attempts,
            "last_error": meta.last_error,
            "last_error_at": meta.last_error_at,
            "last_run": meta.last_run,
            "cancel_requested": bool(self._cancel_flags.get(job_id)),
            "next_run": next_run,
            "description": meta.description,
            "tag": meta.tag,
            "success_count": meta.success_count,
            "failure_count": meta.failure_count,
            "recent_runs": list(meta.recent_runs),
        }

    def cancel_job(self, job_id: str) -> str:
        try:
            self.scheduler.remove_job(job_id)
            meta = self.jobs.get(job_id)
            if meta:
                meta.status = "CANCELLED"
                self._record_run(meta, "CANCELLED", detail="manual_cancel")
            self._cancel_flags.pop(job_id, None)
            return "cancelled"
        except Exception:
            pass
        self._cancel_flags[job_id] = True
        return "cancel_requested"

    def get_recent_runs(self, job_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        meta = self.jobs.get(job_id)
        if not meta:
            return []
        return list(meta.recent_runs)[:limit]

jobs_manager = JobsManager()






