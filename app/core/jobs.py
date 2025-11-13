from __future__ import annotations

import io
import json
import shutil
import zipfile
import asyncio
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

from app.core.llm import LLMClient, build_chat_messages


logger = get_logger("server")


RETRY_DELAYS = [5, 15, 45]  # seconds
RECENT_RUNS_LIMIT = 20


@dataclass
class JobMeta:
    id: str
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    schedule: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    status: str = "PENDING"  # PENDING | RUNNING | SUCCESS | FAILED | RETRYING | CANCELLED
    last_error: Optional[str] = None
    last_run: Optional[str] = None
    description: Optional[str] = None
    tag: Optional[str] = None
    recent_runs: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=RECENT_RUNS_LIMIT))


class JobsManager:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.scheduler = BackgroundScheduler(daemon=True)
        self.jobs: Dict[str, JobMeta] = {}
        self._cancel_flags: Dict[str, bool] = {}
        self._running: Dict[str, bool] = {}
        self._needs_scheduler_rebuild = False

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
        if self.scheduler.running:
            return
        if self._needs_scheduler_rebuild:
            self._rebuild_scheduler()
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self._needs_scheduler_rebuild = True

    def _rebuild_scheduler(self) -> None:
        self.scheduler = BackgroundScheduler(daemon=True)
        for job_id, meta in self.jobs.items():
            if meta.status == "CANCELLED":
                continue
            try:
                trigger = self._build_trigger(meta.schedule)
                self.scheduler.add_job(
                    self._job_wrapper,
                    trigger,
                    args=[job_id],
                    id=job_id,
                    replace_existing=True,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("failed to reschedule job %s during rebuild: %s", job_id, exc)
        self._needs_scheduler_rebuild = False

    # helpers
    def _run_llm(self, prompt: str, options: Optional[Dict[str, Any]] = None, system: str | None = None) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt requis pour le job LLM")
        opts = options or {}
        temperature = float(opts.get("temperature", getattr(self.settings, "llm_temperature", 0.7)))
        max_tokens = int(opts.get("max_tokens", getattr(self.settings, "llm_max_output_tokens", 512)))
        extra_options = {k: v for k, v in opts.items() if k not in {"temperature", "max_tokens"}}
        client = LLMClient(self.settings)
        messages = build_chat_messages(system=system, history=None, prompt=prompt)
        async def _execute() -> dict[str, Any]:
            return await client.chat(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_options=extra_options,
            )

        result = asyncio.run(_execute())
        return result.get("text", "")

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
            self._cancel_flags.pop(job_id, None)
            self._record_run(meta, "CANCELLED", detail="pre_run")
            return
        self._running[job_id] = True
        meta.status = "RUNNING"
        meta.last_run = datetime.now().isoformat()
        self._record_run(meta, "RUNNING")
        try:
            if meta.type == "llm":
                prompt = meta.params.get("prompt", "")
                options = meta.params.get("options")
                system = meta.params.get("system")
                self._run_llm(prompt, options, system=system)
            elif meta.type == "backup":
                path = self._export_backup()
                logger.info(f"Backup exporte: {path}")
            else:
                raise ValueError(f"type de job inconnu: {meta.type}")
            meta.status = "SUCCESS"
            meta.attempts = 0
            meta.last_error = None
            self._record_run(meta, "SUCCESS")
        except Exception as exc:
            meta.attempts += 1
            meta.last_error = str(exc)
            if meta.attempts <= len(RETRY_DELAYS):
                delay = RETRY_DELAYS[meta.attempts - 1]
                meta.status = "RETRYING"
                run_at = datetime.now() + timedelta(seconds=delay)
                self.scheduler.add_job(self._job_wrapper, DateTrigger(run_date=run_at), args=[job_id])
                logger.info(f"Job {job_id} echec, retry dans {delay}s: {exc}")
                self._record_run(meta, "RETRYING", detail=str(exc))
            else:
                meta.status = "FAILED"
                logger.info(f"Job {job_id} FAILED apres retries: {exc}")
                self._record_run(meta, "FAILED", detail=str(exc))
        finally:
            self._running.pop(job_id, None)
            self._cancel_flags.pop(job_id, None)

    def _build_trigger(self, schedule: Dict[str, Any]):
        schedule = schedule or {}
        trigger_type = schedule.get("trigger", "cron")
        if trigger_type == "interval":
            interval_cfg = schedule.get("interval") or {}
            kwargs = {k: v for k, v in interval_cfg.items() if k in {"weeks", "days", "hours", "minutes", "seconds"} and v is not None}
            if not kwargs:
                raise ValueError("interval invalide")
            return IntervalTrigger(**kwargs)
        if trigger_type == "date":
            run_date = schedule.get("date", {}).get("run_date")
            if isinstance(run_date, str):
                try:
                    run_date = datetime.fromisoformat(run_date)
                except ValueError:
                    run_date = None
            if run_date is None:
                run_date = datetime.now() + timedelta(seconds=1)
            return DateTrigger(run_date=run_date)
        cron_cfg = schedule.get("cron") or {}
        minute = cron_cfg.get("minute", 0)
        hour = cron_cfg.get("hour", 3)
        kwargs = {"minute": minute, "hour": hour}
        day_of_week = cron_cfg.get("day_of_week")
        if day_of_week:
            kwargs["day_of_week"] = day_of_week
        return CronTrigger(**kwargs)

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
        sanitized_schedule = schedule or {}
        meta = JobMeta(
            id=job_id,
            type=job_type,
            params=params,
            schedule=sanitized_schedule,
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
        self._cancel_flags.pop(job_id, None)
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
            "last_run": meta.last_run,
            "cancel_requested": bool(self._cancel_flags.get(job_id)),
            "next_run": next_run,
            "description": meta.description,
            "tag": meta.tag,
            "recent_runs": list(meta.recent_runs),
        }

    def cancel_job(self, job_id: str) -> str:
        try:
            self.scheduler.remove_job(job_id)
            meta = self.jobs.get(job_id)
            if meta:
                meta.status = "CANCELLED"
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




