from __future__ import annotations

import io
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings, get_settings
from app.core.logger import get_logger
from app.core import plugins as plugins_module
from app.core.llm import LLM


logger = get_logger("server")


RETRY_DELAYS = [5, 15, 45]  # seconds


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


class JobsManager:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.scheduler = BackgroundScheduler(daemon=True)
        self.jobs: Dict[str, JobMeta] = {}
        self._cancel_flags: Dict[str, bool] = {}
        self._running: Dict[str, bool] = {}

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
        llm = LLM()
        return llm.infer(prompt, options)

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
            return
        self._running[job_id] = True
        meta.status = "RUNNING"
        meta.last_run = datetime.now().isoformat()
        try:
            if meta.type == "plugin":
                if self._cancel_flags.get(job_id):
                    meta.status = "CANCELLED"
                    return
                self._run_plugin(meta.params.get("name", ""), meta.params.get("params", {}))
            elif meta.type == "llm":
                prompt = meta.params.get("prompt", "")
                options = meta.params.get("options")
                if self._cancel_flags.get(job_id):
                    meta.status = "CANCELLED"
                    return
                _ = self._run_llm(prompt, options)
            elif meta.type == "backup":
                path = self._export_backup()
                logger.info(f"Backup exportÃ©: {path}")
            meta.status = "SUCCESS"
            meta.attempts = 0
            meta.last_error = None
        except Exception as exc:  # planifier retry
            meta.attempts += 1
            meta.last_error = str(exc)
            if meta.attempts <= len(RETRY_DELAYS):
                delay = RETRY_DELAYS[meta.attempts - 1]
                meta.status = "RETRYING"
                run_at = datetime.now() + timedelta(seconds=delay)
                if delay == 0:
                    # Retry immédiatement sans replanifier (évite erreurs d'exécuteur arrêté)
                    self._job_wrapper(job_id)
                else:
                    self.scheduler.add_job(self._job_wrapper, DateTrigger(run_date=run_at), args=[job_id])
                logger.info(f"Job {job_id} Ã©chec, retry dans {delay}s: {exc}")
            else:
                meta.status = "FAILED"
                logger.info(f"Job {job_id} FAILED aprÃ¨s retries: {exc}")
        finally:
            self._running.pop(job_id, None)

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
        return job_id

    def remove_job(self, job_id: str) -> bool:
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass
        return self.jobs.pop(job_id, None) is not None

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
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "last_run": meta.last_run if meta else None,
                    "description": meta.description if meta else None,
                    "tag": meta.tag if meta else None,
                }
            )
        # inclure jobs sans entrÃ©e scheduler (p.ex. FAILED)
        for jid, meta in self.jobs.items():
            if not any(x["id"] == jid for x in items):
                items.append(
                    {
                        "id": jid,
                        "type": meta.type,
                        "status": meta.status,
                        "attempts": meta.attempts,
                        "next_run": None,
                        "last_run": meta.last_run,
                        "description": meta.description,
                        "tag": meta.tag,
                    }
                )
        return items

    def run_now(self, job_id: str) -> bool:
        if job_id not in self.jobs:
            return False
        # planifie une exÃ©cution immÃ©diate
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
            # rescheduler le job
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
        return True

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        meta = self.jobs.get(job_id)
        if not meta:
            return None
        # tenter de retrouver next_run_time cÃ´tÃ© scheduler
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
            "last_run": meta.last_run,
            "cancel_requested": bool(self._cancel_flags.get(job_id)),
            "next_run": next_run,
            "description": meta.description,
            "tag": meta.tag,
        }

    def cancel_job(self, job_id: str) -> str:
        # Si le job est programmÃ© (non en cours), on le supprime du scheduler
        try:
            self.scheduler.remove_job(job_id)
            meta = self.jobs.get(job_id)
            if meta:
                meta.status = "CANCELLED"
            return "cancelled"
        except Exception:
            pass
        # Sinon, marquer le flag et laisser l'exÃ©cution courante respecter l'annulation
        self._cancel_flags[job_id] = True
        return "cancel_requested"


jobs_manager = JobsManager()





