from __future__ import annotations

from typing import Any, Dict

from app.core.jobs import jobs_manager


class Plugin:
    meta = {
        "name": "tasks",
        "permissions": ["fs_read"],
        "description": "Gestion des tâches (CRUD) via scheduler",
        "inputs": {},
    }

    def run(self, action: str, spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
        spec = spec or {}
        if action == "create":
            job_type = spec.get("type")
            params = spec.get("params") or {}
            schedule = spec.get("schedule") or {}
            jid = jobs_manager.add_job(
                job_type,
                params,
                schedule,
                description=spec.get("description"),
                tag=spec.get("tag"),
            )
            return {"id": jid}
        if action == "update":
            jid = spec.get("id")
            params = spec.get("params")
            schedule = spec.get("schedule")
            ok = jobs_manager.update_job(
                jid,
                params=params,
                schedule=schedule,
                description=spec.get("description"),
                tag=spec.get("tag"),
            )
            return {"updated": bool(ok)}
        if action == "delete":
            jid = spec.get("id")
            ok = jobs_manager.remove_job(jid)
            return {"deleted": bool(ok)}
        if action == "run_now":
            jid = spec.get("id")
            ok = jobs_manager.run_now(jid)
            return {"scheduled": bool(ok)}
        if action == "list":
            return {"jobs": jobs_manager.list_jobs()}
        if action == "get":
            jid = spec.get("id")
            item = jobs_manager.get_job(jid)
            return {"job": item}
        raise ValueError(f"action inconnue: {action}")


plugin = Plugin()
