from __future__ import annotations

from fastapi import APIRouter, Depends
import httpx
import difflib
import unicodedata
from pydantic import BaseModel
from typing import Any
import logging
import json
from pathlib import Path

from app.core.config import Settings
from app.core.security import require_jwt_or_api_key

router = APIRouter(prefix="/jeedom", tags=["jeedom"])
logger = logging.getLogger(__name__)
INTENT_STORE = Path("app/data/jeedom_intents.json")


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


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized.lower()


def _score_match(query_norm: str, candidate_norm: str) -> float:
    if not candidate_norm:
        return 0.0
    if query_norm in candidate_norm:
        return 1.0
    return difflib.SequenceMatcher(None, query_norm, candidate_norm).ratio()


def _load_intents() -> list[dict]:
    if not INTENT_STORE.is_file():
        return []
    try:
        raw = INTENT_STORE.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_intents(entries: list[dict]) -> None:
    try:
        INTENT_STORE.parent.mkdir(parents=True, exist_ok=True)
        INTENT_STORE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Impossible d'écrire jeedom_intents.json", exc_info=True)


class CommandExec(BaseModel):
    id: str
    value: str | int | float | None = None
    params: dict[str, str | int | float | None] | None = None


class ScenarioExec(BaseModel):
    id: str
    action: str = "start"


class ResolveIntent(BaseModel):
    query: str
    execute: bool | None = False


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


@router.post("/resolve")
async def jeedom_resolve_intent(payload: ResolveIntent, _: None = Depends(require_jwt_or_api_key)) -> dict:
    """
    Tente de résoudre une commande Jeedom à partir d'une phrase (query).
    Heuristiques simples : recherche dans noms d'objets/équipements/commandes.
    Si execute=True et une seule commande matchée, l'exécute.
    """
    settings = Settings()
    try:
        resp = await _jeedom_get(settings, {"type": "fullData"})
        raw_text = (resp.text or "").strip()
        try:
            data = resp.json()
        except Exception:
            data = raw_text
        objects, eqs, commands = _extract_full_data(data)
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}

    query_norm = _normalize(payload.query)
    if not query_norm:
        return {"error": "query vide"}

    # 1) Lookup dans les intents mémorisés
    stored = _load_intents()
    best_intent = None
    best_score = 0.0
    for intent in stored:
        cand_norm = _normalize(intent.get("query"))
        score = _score_match(query_norm, cand_norm)
        if score > best_score:
            best_score = score
            best_intent = intent

    executed = None
    memory_hit = None
    if best_intent and best_score >= 0.7:
        memory_hit = {"intent": best_intent, "score": round(best_score, 3)}
        if payload.execute and best_intent.get("cmd_id"):
            try:
                exec_resp = await _jeedom_get(settings, {"type": "cmd", "id": best_intent["cmd_id"]})
                executed = {
                    "id": best_intent["cmd_id"],
                    "status_code": exec_resp.status_code,
                    "raw_preview": (exec_resp.text or "").strip()[:200],
                    "source": "memory",
                }
            except Exception as exc:  # pragma: no cover - depends on remote Jeedom
                executed = {"id": best_intent["cmd_id"], "error": str(exc), "source": "memory"}

    # Prépare mapping objets et équipements
    object_name: dict[str, str] = {}
    for obj in objects:
        if isinstance(obj, dict) and obj.get("id") is not None:
            object_name[str(obj.get("id"))] = obj.get("name") or ""

    eq_name: dict[str, str] = {}
    eq_type: dict[str, str] = {}
    for eq in eqs:
        if isinstance(eq, dict) and eq.get("id") is not None:
            eq_name[str(eq.get("id"))] = eq.get("name") or ""
            eq_type[str(eq.get("id"))] = eq.get("eqType_name") or ""

    candidates: list[dict] = []
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        cmd_id = cmd.get("id")
        if cmd_id is None:
            continue
        cmd_id_str = str(cmd_id)
        eq_id = cmd.get("eq_id") or cmd.get("eqId") or cmd.get("eqLogic_id") or cmd.get("eqLogicId")
        eq_id_str = str(eq_id) if eq_id is not None else ""
        labels = [
            cmd.get("name"),
            cmd.get("logicalId"),
            cmd.get("type"),
            cmd.get("subType"),
            eq_name.get(eq_id_str, ""),
            eq_type.get(eq_id_str, ""),
            object_name.get(str(eq.get("object_id")), ""),
        ]
        merged = " ".join(filter(None, [str(x) for x in labels]))
        score = _score_match(query_norm, _normalize(merged))
        if score < 0.35:
            continue
        candidates.append(
            {
                "id": cmd_id_str,
                "name": cmd.get("name"),
                "eq_id": eq_id,
                "eq_name": eq_name.get(eq_id_str),
                "type": cmd.get("type"),
                "subType": cmd.get("subType"),
                "score": round(score, 3),
            }
        )

    candidates_sorted = sorted(candidates, key=lambda x: x["score"], reverse=True)

    if executed is None and payload.execute and len(candidates_sorted) == 1:
        target = candidates_sorted[0]
        try:
            exec_resp = await _jeedom_get(settings, {"type": "cmd", "id": target["id"]})
            executed = {
                "id": target["id"],
                "status_code": exec_resp.status_code,
                "raw_preview": (exec_resp.text or "").strip()[:200],
                "source": "search",
            }
        except Exception as exc:  # pragma: no cover - depends on remote Jeedom
            executed = {"id": target["id"], "error": str(exc), "source": "search"}

    # 2) Sauvegarde l'intention si exécutée et pas déjà présente
    if executed and executed.get("status_code") and executed["status_code"] == 200:
        exists = any(
            _normalize(intent.get("query")) == query_norm and intent.get("cmd_id") == executed.get("id")
            for intent in stored
        )
        if not exists:
            stored.append(
                {
                    "query": payload.query,
                    "cmd_id": executed.get("id"),
                    "ts": None,
                    "source": executed.get("source"),
                }
            )
            _save_intents(stored)

    return {
        "matched": candidates_sorted[:10],
        "matched_count": len(candidates_sorted),
        "executed": executed,
        "memory_hit": memory_hit,
        "status_code": resp.status_code if "resp" in locals() else None,
    }


@router.get("/catalog")
async def jeedom_catalog(_: None = Depends(require_jwt_or_api_key)) -> dict:
    """
    Retourne un catalogue structuré (objets, équipements, commandes) pour alimenter un prompt LLM.
    """
    settings = Settings()
    try:
        resp = await _jeedom_get(settings, {"type": "fullData"})
        raw_text = (resp.text or "").strip()
        try:
            data = resp.json()
        except Exception:
            data = raw_text
        objects, eqs, cmds = _extract_full_data(data)
        return {
            "objects": [
                {"id": obj.get("id"), "name": obj.get("name")}
                for obj in objects
                if isinstance(obj, dict)
            ],
            "equipments": [
                {
                    "id": eq.get("id"),
                    "name": eq.get("name"),
                    "type": eq.get("eqType_name"),
                    "object_id": eq.get("object_id"),
                }
                for eq in eqs
                if isinstance(eq, dict)
            ],
            "commands": [
                {
                    "id": cmd.get("id"),
                    "name": cmd.get("name"),
                    "type": cmd.get("type"),
                    "subType": cmd.get("subType"),
                    "eq_id": cmd.get("eq_id")
                    or cmd.get("eqId")
                    or cmd.get("eqLogic_id")
                    or cmd.get("eqLogicId"),
                    "logicalId": cmd.get("logicalId"),
                }
                for cmd in cmds
                if isinstance(cmd, dict)
            ],
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
