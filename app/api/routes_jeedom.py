from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Body
import httpx
import difflib
import unicodedata
from pydantic import BaseModel
from typing import Any
import logging
import json
from pathlib import Path
from datetime import datetime
from time import monotonic
import asyncio
import os
from collections import deque

from app.core.config import Settings
from app.core.security import require_jwt_or_api_key
from app.core.llm import LLM

router = APIRouter(prefix="/jeedom", tags=["jeedom"])
logger = logging.getLogger(__name__)
INTENT_STORE = Path("app/data/jeedom_intents.json")
INTENT_STORE_TMP = Path("app/data/jeedom_intents_tmp.json")
INTENT_STORE_WEB = Path("webui/public/jeedom_intents.json")
_FULLDATA_CACHE: dict[str, object] = {}
_FULLDATA_CACHE_TTL = 60.0
_FULLDATA_LOCK = asyncio.Lock()
_JEEDOM_TRACES: deque[dict[str, object]] = deque(maxlen=15)


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
    normalized = normalized.lower()
    # Remplacer les caracteres corrompus/latin-1 approximatifs
    normalized = normalized.replace("ゼ", "e").replace("キ", "c").replace("オ", "o").replace("ゼ", "e").replace("Ь", "e")
    normalized = normalized.replace("Ё", "e").replace("キ", "c")
    normalized = normalized.replace("ゼ", "e")
    return normalized


def _score_match(query_norm: str, candidate_norm: str) -> float:
    if not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 1.0
    # Si la requête contient le candidat (ex: "allume la lumiere du bureau" contient "allume bureau")
    if candidate_norm in query_norm:
        return 0.95
    if query_norm in candidate_norm:
        return 0.95
    return difflib.SequenceMatcher(None, query_norm, candidate_norm).ratio()


_SYNONYMS = {
    "lumiere": ["lampe", "light", "lumieres", "lampes"],
    "chauffage": ["radiateur", "thermostat"],
    "prise": ["switch", "prise connectee"],
    "volet": ["store", "rideau"],
}


def _expand_synonyms(text: str) -> str:
    tokens = text.split()
    expanded: list[str] = []
    for tok in tokens:
        expanded.append(tok)
        for base, alts in _SYNONYMS.items():
            if tok.startswith(base):
                expanded.extend(alts)
            if tok in alts:
                expanded.append(base)
    return " ".join(expanded)


def _load_intents() -> list[dict]:
    candidates = [INTENT_STORE, INTENT_STORE_TMP, INTENT_STORE_WEB]
    for path in candidates:
        if not path.is_file():
            continue
        # Lecture tolérante (utf-8 puis fallback)
        for enc in ("utf-8", "cp1252"):
            try:
                raw = path.read_text(encoding=enc, errors="ignore")
                data = json.loads(raw)
                if isinstance(data, list):
                    cleaned = []
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        q = item.get("query")
                        cid = item.get("cmd_id")
                        if not q or not cid:
                            continue
                        cleaned.append(
                            {
                                "query": str(q),
                                "cmd_id": str(cid),
                                "source": item.get("source"),
                                "ts": item.get("ts"),
                            }
                        )
                    if cleaned:
                        return cleaned
            except Exception:
                continue
    return []


def _save_intents(entries: list[dict]) -> None:
    try:
        INTENT_STORE.parent.mkdir(parents=True, exist_ok=True)
        INTENT_STORE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Impossible d'écrire jeedom_intents.json", exc_info=True)


def _append_intent(query: str, cmd_id: str, source: str | None = None) -> None:
    entries = _load_intents()
    query_norm = _normalize(query)
    for intent in entries:
        if _normalize(intent.get("query")) == query_norm and intent.get("cmd_id") == cmd_id:
            return
    if not query:
        return
    if not cmd_id:
        return
    entries.append(
        {
            "query": query,
            "cmd_id": cmd_id,
            "source": source,
            "ts": datetime.utcnow().isoformat() + "Z",
        }
    )
    _save_intents(entries)
    # miroir éventuel côté webui/public pour debug/partage
    try:
        INTENT_STORE_WEB.parent.mkdir(parents=True, exist_ok=True)
        INTENT_STORE_WEB.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Impossible d'écrire jeedom_intents.json côté webui", exc_info=True)


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


def _invalidate_full_data_cache() -> None:
    _FULLDATA_CACHE.clear()


async def _get_full_data_cached(settings: Settings, *, force: bool = False) -> tuple[object, str, int]:
    now = monotonic()
    async with _FULLDATA_LOCK:
        ts = _FULLDATA_CACHE.get("ts")
        if (
            not force
            and isinstance(ts, (int, float))
            and now - float(ts) < _FULLDATA_CACHE_TTL
            and "data" in _FULLDATA_CACHE
        ):
            return (
                _FULLDATA_CACHE["data"],
                str(_FULLDATA_CACHE.get("raw", "")),
                int(_FULLDATA_CACHE.get("status_code", 0) or 0),
            )

    resp = await _jeedom_get(settings, {"type": "fullData"})
    raw_text = (resp.text or "").strip()
    if resp.status_code != 200:
        raise RuntimeError(f"Jeedom fullData a renvoye {resp.status_code}: {raw_text[:200]}")
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"Jeedom fullData reponse non JSON: {raw_text[:200]}")
    if not isinstance(data, (dict, list)):
        raise RuntimeError("Jeedom fullData reponse inattendue (ni dict ni liste)")

    async with _FULLDATA_LOCK:
        _FULLDATA_CACHE["ts"] = now
        _FULLDATA_CACHE["data"] = data
        _FULLDATA_CACHE["raw"] = raw_text
        _FULLDATA_CACHE["status_code"] = resp.status_code

    return data, raw_text, resp.status_code


async def _jeedom_get(settings: Settings, params: dict) -> httpx.Response:
    base_url = settings.jeedom_base_url
    api_key = settings.jeedom_api_key
    if not base_url or not api_key:
        raise RuntimeError("jeedom_base_url ou jeedom_api_key manquants")
    allowed = getattr(settings, "jeedom_allowed_hosts", []) or []
    try:
        host = httpx.URL(base_url).host
    except Exception:
        host = None
    if allowed and host and host not in allowed:
        raise RuntimeError(f"Host Jeedom non autorise: {host}")
    url = f"{base_url.rstrip('/')}/core/api/jeeApi.php"
    full_params = {"apikey": api_key}
    full_params.update(params)
    timeout = float(getattr(settings, "jeedom_timeout", 10.0) or 10.0)

    async def _do_call() -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout, verify=settings.jeedom_verify_ssl) as client:
            return await client.get(url, params=full_params)

    try:
        resp = await _do_call()
    except httpx.TimeoutException:
        # Retry léger une fois
        resp = await _do_call()

    try:
        trace = {
            "params": {k: v for k, v in full_params.items() if k != "apikey"},
            "url": url,
            "status_code": getattr(resp, "status_code", None),
            "body_preview": (getattr(resp, "text", "") or "").strip()[:200],
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        _JEEDOM_TRACES.append(trace)
    except Exception:
        pass

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
            "verify_ssl": settings.jeedom_verify_ssl,
            "timeout": getattr(settings, "jeedom_timeout", 10.0),
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {
            "configured": configured,
            "base_url": base_url,
            "reachable": False,
            "error": str(exc),
            "verify_ssl": settings.jeedom_verify_ssl,
            "timeout": getattr(settings, "jeedom_timeout", 10.0),
        }


@router.get("/equipments")
async def jeedom_equipments(_: None = Depends(require_jwt_or_api_key)) -> dict:
    """Retourne la liste des équipements Jeedom (fullData) + objets."""
    settings = Settings()
    try:
        data, raw_text, status_code = await _get_full_data_cached(settings)
        objects, items, _ = _extract_full_data(data)
        object_map = {
            str(obj.get("id")): obj.get("name")
            for obj in objects
            if isinstance(obj, dict) and obj.get("id") is not None
        }
        return {
            "status_code": status_code,
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
        data, raw_text, status_code = await _get_full_data_cached(settings)
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
                normalized.setdefault("eq_name", next((eq.get("name") for eq in eq_logics if str(eq.get("id")) == str(normalized.get("eq_id"))), None))
                normalized_commands.append(normalized)

        return {
            "status_code": status_code,
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
        _invalidate_full_data_cache()
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
        _invalidate_full_data_cache()
        raw_text = (resp.text or "").strip()
        return {
            "status_code": resp.status_code,
            "raw_preview": raw_text[:200],
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}


@router.post("/resolve")
async def jeedom_resolve_intent(
    payload: ResolveIntent | None = Body(default=None),
    query: str | None = Query(default=None),
    execute: bool | None = Query(default=None),
    _: None = Depends(require_jwt_or_api_key),
) -> dict:
    """
    Tente de résoudre une commande Jeedom à partir d'une phrase (query).
    Heuristiques simples : recherche dans noms d'objets/équipements/commandes.
    Si execute=True et une seule commande matchée, l'exécute.
    """
    settings = Settings()
    try:
        data, raw_text, status_code = await _get_full_data_cached(settings)
        objects, eqs, commands = _extract_full_data(data)
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}

    final_query = (payload.query if payload else None) or query
    query_norm = _normalize(final_query)
    if not query_norm:
        return {"error": "query vide"}

    exec_flag = payload.execute if payload and payload.execute is not None else execute

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
        if (exec_flag or exec_flag is None) and best_intent.get("cmd_id"):
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
    eq_object: dict[str, str] = {}
    for eq in eqs:
        if isinstance(eq, dict) and eq.get("id") is not None:
            eq_name[str(eq.get("id"))] = eq.get("name") or ""
            eq_type[str(eq.get("id"))] = eq.get("eqType_name") or ""
            if eq.get("object_id") is not None:
                eq_object[str(eq.get("id"))] = str(eq.get("object_id"))

    query_syn = _expand_synonyms(query_norm)
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
        obj_name = object_name.get(eq_object.get(eq_id_str, "") or "", "")
        labels = [
            cmd.get("name"),
            cmd.get("logicalId"),
            cmd.get("type"),
            cmd.get("subType"),
            eq_name.get(eq_id_str, ""),
            eq_type.get(eq_id_str, ""),
            obj_name,
        ]
        merged = " ".join(filter(None, [str(x) for x in labels]))
        merged_norm = _normalize(merged)
        merged_syn = _expand_synonyms(merged_norm)
        score = max(_score_match(query_norm, merged_norm), _score_match(query_syn, merged_syn))
        eqn_norm = _normalize(eq_name.get(eq_id_str, ""))
        cmd_name_norm = _normalize(cmd.get("name"))
        is_action = (cmd.get("type") or "").lower() == "action"
        if eqn_norm and eqn_norm in query_norm:
            score += 0.3
        if is_action:
            if ("allume" in query_norm or "on" in query_norm) and ("on" in cmd_name_norm or "allume" in cmd_name_norm):
                score += 0.3
            if ("etein" in query_norm or "off" in query_norm) and ("off" in cmd_name_norm or "etein" in cmd_name_norm):
                score += 0.3
        score = min(score, 1.5)
        if score < 0.35:
            continue
        candidates.append(
            {
                "id": cmd_id_str,
                "name": cmd.get("name"),
                "eq_id": eq_id,
                "eq_name": eq_name.get(eq_id_str),
                "eq_type": eq_type.get(eq_id_str),
                "object_name": obj_name,
                "type": cmd.get("type"),
                "subType": cmd.get("subType"),
                "score": round(score, 3),
            }
        )

    candidates_sorted = sorted(candidates, key=lambda x: x["score"], reverse=True)

    need_confirmation = False
    if executed is None and (exec_flag or exec_flag is None):
        target = None
        if len(candidates_sorted) == 1:
            target = candidates_sorted[0]
        elif candidates_sorted:
            best = candidates_sorted[0]
            if len(candidates_sorted) >= 2:
                second = candidates_sorted[1]
                if best.get("score", 0) >= 0.5 and abs(best.get("score", 0) - second.get("score", 0)) < 0.05:
                    need_confirmation = True
            if best.get("score", 0) >= 0.5:
                target = best
        if target:
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
            _append_intent(final_query or "", executed.get("id"), executed.get("source"))

    return {
        "matched": candidates_sorted[:10],
        "matched_count": len(candidates_sorted),
        "executed": executed,
        "memory_hit": memory_hit,
        "exec_flag": exec_flag,
        "status_code": status_code if "status_code" in locals() else None,
        "need_confirmation": need_confirmation,
    }


@router.get("/resolve")
async def jeedom_resolve_intent_get(
    query: str,
    execute: bool | None = None,
    _: None = Depends(require_jwt_or_api_key),
) -> dict:
    """Alias GET pour resolve (utile pour debug sans corps JSON)."""
    payload = ResolveIntent(query=query, execute=execute)
    return await jeedom_resolve_intent(payload=payload, query=query, execute=execute, _=_)


@router.get("/traces")
async def jeedom_traces(_: None = Depends(require_jwt_or_api_key)) -> dict:
    """Retourne les derniers appels Jeedom (params sans apikey, status, preview)."""
    return {"items": list(_JEEDOM_TRACES)}


@router.get("/catalog")
async def jeedom_catalog(_: None = Depends(require_jwt_or_api_key)) -> dict:
    """
    Retourne un catalogue structuré (objets, équipements, commandes) pour alimenter un prompt LLM.
    """
    settings = Settings()
    try:
        data, raw_text, status_code = await _get_full_data_cached(settings)
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
            "status_code": status_code,
            "raw_preview": raw_text[:200],
        }
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}


@router.get("/intents")
async def jeedom_intents_list(_: None = Depends(require_jwt_or_api_key)) -> dict:
    """Retourne les intentions mémorisées (query -> cmd_id)."""
    entries = _load_intents()
    return {"count": len(entries), "items": entries}


@router.post("/intents")
async def jeedom_intent_add(
    payload: dict | None = Body(default=None),
    cmd_id: str | None = Query(default=None),
    query: str | None = Query(default=None),
    _: None = Depends(require_jwt_or_api_key),
) -> dict:
    """Ajoute manuellement une intention (query -> cmd_id)."""
    final_query = (payload or {}).get("query") if payload else query
    final_cmd_id = (payload or {}).get("cmd_id") if payload else cmd_id
    if not final_query or not final_cmd_id:
        return {"error": "query et cmd_id requis"}
    _append_intent(str(final_query), str(final_cmd_id), "manual")
    items = _load_intents()
    return {"status": "added", "count": len(items)}


@router.delete("/intents")
async def jeedom_intent_delete(cmd_id: str | None = None, query: str | None = None, _: None = Depends(require_jwt_or_api_key)) -> dict:
    """
    Supprime les intentions correspondant à cmd_id ou query (au moins un des deux).
    """
    entries = _load_intents()
    if not cmd_id and not query:
        return {"error": "cmd_id ou query requis"}
    filtered: list[dict] = []
    removed = 0
    for intent in entries:
        match_cmd = cmd_id and intent.get("cmd_id") == cmd_id
        match_query = query and _normalize(intent.get("query")) == _normalize(query)
        if match_cmd or match_query:
            removed += 1
            continue
        filtered.append(intent)
    _save_intents(filtered)
    return {"removed": removed, "count": len(filtered)}


@router.delete("/intents/all")
async def jeedom_intents_clear(_: None = Depends(require_jwt_or_api_key)) -> dict:
    """Supprime toutes les intentions mémorisées."""
    _save_intents([])
    return {"status": "cleared"}


def _build_catalog_for_llm(objects: list[dict], eqs: list[dict], cmds: list[dict], limit_cmds: int = 120) -> str:
    object_name: dict[str, str] = {}
    for obj in objects:
        if isinstance(obj, dict) and obj.get("id") is not None:
            object_name[str(obj.get("id"))] = obj.get("name") or ""

    eq_map: dict[str, dict] = {}
    for eq in eqs:
        if isinstance(eq, dict) and eq.get("id") is not None:
            eq_map[str(eq.get("id"))] = eq

    lines: list[str] = []
    for cmd in cmds[:limit_cmds]:
        if not isinstance(cmd, dict):
            continue
        cmd_id = cmd.get("id")
        if cmd_id is None:
            continue
        eq_id = cmd.get("eq_id") or cmd.get("eqId") or cmd.get("eqLogic_id") or cmd.get("eqLogicId")
        eq_id_str = str(eq_id) if eq_id is not None else ""
        eq_entry = eq_map.get(eq_id_str, {})
        obj_name = object_name.get(str(eq_entry.get("object_id")), "")
        line = f"id={cmd_id} name={cmd.get('name')} eq={eq_entry.get('name','?')} obj={obj_name or '-'} type={cmd.get('type')} sub={cmd.get('subType')}"
        lines.append(line)
    return "\n".join(lines)


@router.post("/intents/auto")
async def jeedom_intents_auto(
    instructions: str | None = Body(default=None, embed=True),
    limit_cmds: int = Query(default=120, ge=10, le=400),
    offset_cmds: int = Query(default=0, ge=0),
    max_intents: int = Query(default=30, ge=5, le=200),
    target_cmd_ids: list[str] | None = Body(default=None, embed=True),
    _: None = Depends(require_jwt_or_api_key),
) -> dict:
    """
    Génère des intentions (query -> cmd_id) via LLM à partir du catalogue Jeedom.
    """
    settings = Settings()
    model_path = os.environ.get("LLM_MODEL_PATH")
    if model_path is None:
        return {"error": "LLM_MODEL_PATH non configuré"}

    try:
        data, raw_text, status_code = await _get_full_data_cached(settings)
        objects, eqs, cmds = _extract_full_data(data)
    except Exception as exc:  # pragma: no cover - depends on remote Jeedom
        return {"error": str(exc)}

    selected_cmds = cmds[offset_cmds : offset_cmds + limit_cmds]
    if target_cmd_ids:
        target_set = {str(x) for x in target_cmd_ids}
        selected_cmds = [c for c in selected_cmds if str(c.get("id")) in target_set]

    catalog_snippet = _build_catalog_for_llm(objects, eqs, selected_cmds, limit_cmds=limit_cmds)
    sys_prompt = "\n".join(
        [
            "Tu es configurateur Jeedom. On te fournit une liste de commandes (id, nom, équipement, objet, type, subtype).",
            "Objectif : proposer des intentions naturelles en français qui mappent directement vers les ids de commande.",
            "Règles :",
            "- Ne pas inventer d'id ni de commande.",
            f"- Générer entre 5 et {max_intents} intentions maximum.",
            '- Utilise des tournures simples : ex: "allume bureau", "éteins bureau", "statut bureau", "lance scénario chauffage".',
            "- Inclure ON/OFF si une commande s'y prête (type action, nom contenant on/off).",
            "- Retourne uniquement du JSON au format:",
            '[{"query":"allume bureau","cmd_id":"1616","note":"on bureau"}, {"query":"éteins bureau","cmd_id":"1615","note":"off bureau"}]',
        ]
    )
    if instructions:
        sys_prompt += f"\nConsignes supplémentaires : {instructions}\n"
    sys_prompt += "\nCatalogue (limité):\n" + catalog_snippet

    llm = LLM(model_path)
    try:
        raw_out = await asyncio.to_thread(
            llm.infer,
            sys_prompt,
            {"max_tokens": settings.llm_max_output_tokens, "temperature": 0.3},
        )
    except Exception as exc:  # pragma: no cover - depends on local LLM
        return {"error": str(exc)}

    def _normalize_text_output(raw: Any) -> str:
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
            return "".join(raw)
        try:
            return json.dumps(raw, ensure_ascii=False)
        except Exception:
            return str(raw)

    text_out = _normalize_text_output(raw_out)

    def _extract_suggestions(txt: str) -> list[dict]:
        # 1) tentative directe
        try:
            data = json.loads(txt)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        # 2) code fence ```json ... ```
        if "```" in txt:
            parts = txt.split("```")
            for part in parts:
                if "[" in part and "]" in part:
                    try:
                        data = json.loads(part[part.find("[") : part.rfind("]") + 1])
                        if isinstance(data, list):
                            return data
                    except Exception:
                        continue
        # 3) extraction brute de [ ... ]
        start = txt.find("[")
        end = txt.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(txt[start : end + 1])
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return []

    suggestions = _extract_suggestions(text_out)

    added = 0
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        q = item.get("query")
        cid = item.get("cmd_id")
        if not q or not cid:
            continue
        _append_intent(str(q), str(cid), "auto")
        added += 1

    return {
        "generated": suggestions,
        "added": added,
        "status_code": status_code if "status_code" in locals() else None,
        "raw_model_output": text_out[:500] if isinstance(text_out, str) else str(text_out)[:500],
    }


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
