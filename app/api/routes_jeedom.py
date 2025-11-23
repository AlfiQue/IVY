from __future__ import annotations

from fastapi import APIRouter, Depends
import httpx
from pydantic import BaseModel
from typing import Any
import logging

from app.core.config import Settings
from app.core.security import require_jwt_or_api_key

router = APIRouter(prefix="/jeedom", tags=["jeedom"])
logger = logging.getLogger(__name__)


def _extract_full_data(data: object) -> tuple[list[dict], list[dict], list[dict]]:
    """Extrait objets, équipements et commandes d'une réponse fullData Jeedom."""
    objects: list[dict] = []
    eq_logics: list[dict] = []
    commands: list[dict] = []

    def _safe_extend(target: list[dict], items: object) -> None:
        for item in items or []:
            if isinstance(item, dict):
                target.append(item)

    if isinstance(data, dict):
        _safe_extend(objects, data.get("objects"))
        _safe_extend(eq_logics, data.get("eqLogics") or data.get("eqlogics"))
        _safe_extend(commands, data.get("cmds") or data.get("commands") or data.get("cmd"))

        if not eq_logics:
            for obj in objects:
                _safe_extend(eq_logics, obj.get("eqLogics") or obj.get("eqlogics"))

        if not commands and eq_logics:
            for eq in eq_logics:
                _safe_extend(commands, eq.get("cmds") or eq.get("commands"))

    elif isinstance(data, list):
        for obj in data:
            if isinstance(obj, dict):
                objects.append(obj)
                _safe_extend(eq_logics, obj.get("eqLogics") or obj.get("eqlogics"))

        if eq_logics:
            for eq in eq_logics:
                _safe_extend(commands, eq.get("cmds") or eq.get("commands"))

    return objects, eq_logics, commands


class CommandExec(BaseModel):
    id: str
    value: str | int | float | None = None
    params: dict[str, str | int | float | None] | None = None


class ScenarioExec(BaseModel):
    id: str
    action: str = "start"


async def _jeedom_get(settings: Settings, params: dict) -> httpx.Response:
    base_url = settings.jeedom_base_url
    api_key = settings.jeedom_api_key
    if not base_url or not api_key:
        raise RuntimeError("jeedom_base_url ou jeedom_api_key manquants")
    url = f"{base_url.rstrip('/')}/core/api/jeeApi.php"
    full_params = {"apikey": api_key}
    full_params.update(params)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=full_params)
    return resp


@router.get("/status")
async def jeedom_status(_: None = Depends(require_jwt_or_api_key)) -> dict:
    settings = Settings()
    base_url = settings.jeedom_base_url
    api_key = settings.jeedom_api_key
    configured = bool(base_url and api_key)
    if not configured:
        return {
            "configured": False,
            "base_url": base_url,
            "reachable": False,
            "message": "base_url ou api_key manquants",
        }

    note = None
    try:
        resp = await _jeedom_get(settings, {"type": "ping"})
        raw_text = (resp.text or "").strip()
        text = raw_text.lower()
        reachable = resp.status_code == 200 and (
            "pong" in text
            or text in {"ok", "success", "1", "true"}
            or text.startswith("pong")
        )
        if not reachable:
            try:
                payload = resp.json()
                if isinstance(payload, dict):
                    result = str(payload.get("result", "")).lower()
                    reachable = reachable or result in {"success", "ok", "1", "true"}
            except Exception:
                pass
        if not reachable and resp.status_code == 200 and not raw_text:
            # Certaines installations renvoient 200 sans corps pour ping; on considère la connexion OK.
            reachable = True
            note = "Réponse vide (200) lors du ping Jeedom."
        return {
            "configured": configured,
            "base_url": base_url,
            "reachable": reachable,
            "status": raw_text or resp.status_code,
            "status_code": resp.status_code,
            "body_preview": raw_text[:200],
            "note": note,
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {
            "configured": configured,
            "base_url": base_url,
            "reachable": False,
            "error": str(exc),
        }


@router.get("/equipments")
async def jeedom_equipments(_: None = Depends(require_jwt_or_api_key)) -> dict:
    """Retourne la liste des équipements Jeedom (fullData) + objets."""
    settings = Settings()
    try:
        resp = await _jeedom_get(settings, {"type": "fullData"})
        raw_text = (resp.text or "").strip()
        try:
            data = resp.json()
        except Exception:
            data = raw_text
        objects, items, _ = _extract_full_data(data)
        object_map = {
            str(obj.get("id")): obj.get("name")
            for obj in objects
            if isinstance(obj, dict) and obj.get("id") is not None
        }
        return {
            "status_code": resp.status_code,
            "count": len(items),
            "items": items,
            "objects": objects,
            "objects_count": len(objects),
            "object_map": object_map,
            "raw_preview": raw_text[:200],
            "source": "fullData",
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}


@router.get("/commands")
async def jeedom_commands(_: None = Depends(require_jwt_or_api_key)) -> dict:
    """Retourne les commandes Jeedom en se basant sur fullData."""
    settings = Settings()
    try:
        resp = await _jeedom_get(settings, {"type": "fullData"})
        raw_text = (resp.text or "").strip()
        try:
            data = resp.json()
        except Exception:
            data = raw_text

        _, eq_logics, commands = _extract_full_data(data)

        if not commands and eq_logics:
            for eq in eq_logics:
                eq_id = eq.get("id")
                eq_name = eq.get("name")
                eq_type = eq.get("eqType_name")
                for cmd in eq.get("cmds") or []:
                    if isinstance(cmd, dict):
                        cmd_copy = dict(cmd)
                        cmd_copy.setdefault("eq_id", eq_id)
                        cmd_copy.setdefault("eq_name", eq_name)
                        cmd_copy.setdefault("eq_type", eq_type)
                        commands.append(cmd_copy)

        normalized_commands: list[dict] = []
        for cmd in commands:
            if isinstance(cmd, dict):
                normalized = dict(cmd)
                normalized.setdefault(
                    "eq_id",
                    cmd.get("eq_id")
                    or cmd.get("eqId")
                    or cmd.get("eqLogic_id")
                    or cmd.get("eqLogicId"),
                )
                normalized_commands.append(normalized)

        return {
            "status_code": resp.status_code,
            "count": len(normalized_commands),
            "items": normalized_commands,
            "raw_preview": raw_text[:200],
            "source": "fullData",
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}


@router.post("/command/run")
async def jeedom_command_run(
    payload: CommandExec | None = None,
    id: str | None = None,
    value: Any | None = None,
    slider: Any | None = None,
    _: None = Depends(require_jwt_or_api_key),
) -> dict:
    """Exécute une commande Jeedom (action) via son ID."""
    settings = Settings()
    try:
        cmd_id = payload.id if payload else id
        if not cmd_id:
            return {"error": "id manquant"}
        chosen_value = payload.value if payload else value
        if chosen_value is None:
            chosen_value = slider

        params: dict[str, object] = {"type": "cmd", "id": cmd_id}
        if chosen_value is not None:
            params["slider"] = chosen_value
            params["value"] = chosen_value
            params["action"] = "slider"
        extra_params = payload.params if payload else None
        if extra_params:
            for key, val in extra_params.items():
                if val is not None:
                    params[str(key)] = val

        base_url = settings.jeedom_base_url or ""
        url = f"{base_url.rstrip('/')}/core/api/jeeApi.php"

        query_parts = []
        for k, v in params.items():
            query_parts.append(f"{k}={v}")
        safe_url = f"{url}?apikey=***&" + "&".join(query_parts)

        log_payload = {"params": params, "url": url, "safe_url": safe_url}
        logger.info("Jeedom cmd call", extra=log_payload)
        try:
            print(f"[Jeedom] CMD -> {log_payload}", flush=True)
        except Exception:
            pass

        resp = await _jeedom_get(settings, params)
        raw_text = (resp.text or "").strip()

        log_response = {"status_code": resp.status_code, "body_preview": raw_text[:200]}
        logger.info("Jeedom cmd response", extra=log_response)
        try:
            print(f"[Jeedom] RESP -> {log_response}", flush=True)
        except Exception:
            pass
        return {
            "status_code": resp.status_code,
            "raw_preview": raw_text[:200],
            "params": params,
            "url": url,
            "safe_url": safe_url,
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}


@router.post("/scenario")
async def jeedom_scenario(payload: ScenarioExec, _: None = Depends(require_jwt_or_api_key)) -> dict:
    """Pilote un scénario Jeedom (start/stop/enable/disable)."""
    settings = Settings()
    try:
        resp = await _jeedom_get(
            settings,
            {
                "type": "scenario",
                "id": payload.id,
                "action": payload.action or "start",
            },
        )
        raw_text = (resp.text or "").strip()
        return {
            "status_code": resp.status_code,
            "raw_preview": raw_text[:200],
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}


@router.get("/raw")
async def jeedom_raw(type: str, _: None = Depends(require_jwt_or_api_key)) -> dict:
    """Retour brut de l'API Jeedom pour un type donné (ex: eqLogic)."""
    settings = Settings()
    try:
        resp = await _jeedom_get(settings, {"type": type})
        raw_text = (resp.text or "").strip()
        try:
            data = resp.json()
        except Exception:
            data = raw_text
        return {
            "status_code": resp.status_code,
            "raw": data,
            "raw_preview": raw_text[:500],
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}
