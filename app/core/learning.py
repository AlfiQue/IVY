"""Auto-learning helpers to log chat interactions and surface insights."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

import aiosqlite

from app.core.db import open_db
from app.core import job_prompts, chat_store
from app.core.jobs import jobs_manager
from app.core.learning_store import list_learning_events, log_learning_event

_INIT_LOCK = asyncio.Lock()
_TABLE_READY = False
_QUESTION_MAX_LEN = 2000
_QUERY_MAX_LEN = 240


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim_text(value: str, limit: int) -> str:
    text = (value or "").strip()
    if len(text) > limit:
        text = text[:limit]
    return text


async def _ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    async with _INIT_LOCK:
        if _TABLE_READY:
            return
        async with open_db() as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    normalized_query TEXT,
                    classification TEXT,
                    needs_search INTEGER NOT NULL DEFAULT 0,
                    search_query TEXT,
                    search_results_count INTEGER NOT NULL DEFAULT 0,
                    latency_ms REAL,
                    origin TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_learning_events_query
                ON learning_events(normalized_query)
                """
            )
            await db.commit()
        _TABLE_READY = True


async def record_event(
    *,
    question: str,
    normalized_query: str,
    classification: dict[str, Any] | None,
    needs_search: bool,
    search_query: str,
    search_results_count: int,
    latency_ms: float,
    origin: str,
) -> None:
    """Persist a learning event for future insights."""
    await _ensure_table()
    payload = json.dumps(classification or {}, ensure_ascii=False)
    async with open_db() as db:
        await db.execute(
            """
            INSERT INTO learning_events (
                question,
                normalized_query,
                classification,
                needs_search,
                search_query,
                search_results_count,
                latency_ms,
                origin,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _trim_text(question, _QUESTION_MAX_LEN),
                _trim_text(normalized_query, _QUERY_MAX_LEN),
                payload,
                1 if needs_search else 0,
                _trim_text(search_query, _QUERY_MAX_LEN),
                max(0, int(search_results_count)),
                float(latency_ms) if latency_ms is not None else None,
                (origin or "llm"),
                _now_iso(),
            ),
        )
        await db.commit()


def record_event_sync(**kwargs: Any) -> None:
    """Fire-and-forget wrapper usable from sync contexts."""

    async def _runner() -> None:
        await record_event(**kwargs)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_runner())
        return

    try:
        loop.create_task(_runner())
    except RuntimeError:
        asyncio.run(_runner())


async def top_queries(limit: int = 10) -> list[dict[str, Any]]:
    await _ensure_table()
    limit = max(1, min(limit, 50))
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                normalized_query,
                COUNT(*) AS occurrences,
                SUM(needs_search) AS needs_search_hits,
                SUM(CASE WHEN search_results_count > 0 THEN 1 ELSE 0 END) AS search_success,
                AVG(latency_ms) AS avg_latency,
                MAX(created_at) AS last_seen
            FROM learning_events
            WHERE normalized_query IS NOT NULL AND normalized_query != ''
            GROUP BY normalized_query
            ORDER BY occurrences DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "query": row["normalized_query"],
                "occurrences": int(row["occurrences"] or 0),
                "needs_search_hits": int(row["needs_search_hits"] or 0),
                "search_success": int(row["search_success"] or 0),
                "avg_latency_ms": float(row["avg_latency"]) if row["avg_latency"] is not None else None,
                "last_seen": row["last_seen"],
            }
        )
    return items


async def unresolved_queries(limit: int = 10) -> list[dict[str, Any]]:
    await _ensure_table()
    limit = max(1, min(limit, 50))
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                normalized_query,
                COUNT(*) AS occurrences,
                MAX(created_at) AS last_seen
            FROM learning_events
            WHERE needs_search = 1
              AND (search_results_count IS NULL OR search_results_count = 0)
              AND normalized_query IS NOT NULL
              AND normalized_query != ''
            GROUP BY normalized_query
            ORDER BY occurrences DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [
        {
            "query": row["normalized_query"],
            "occurrences": int(row["occurrences"] or 0),
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]


async def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    await _ensure_table()
    limit = max(1, min(limit, 100))
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                question,
                normalized_query,
                needs_search,
                search_query,
                search_results_count,
                latency_ms,
                origin,
                classification,
                created_at
            FROM learning_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(row["classification"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        events.append(
            {
                "question": row["question"],
                "normalized_query": row["normalized_query"],
                "needs_search": bool(row["needs_search"]),
                "search_query": row["search_query"],
                "search_results_count": int(row["search_results_count"] or 0),
                "latency_ms": float(row["latency_ms"]) if row["latency_ms"] is not None else None,
                "origin": row["origin"],
                "classification": metadata,
                "created_at": row["created_at"],
            }
        )
    return events


def _format_prompt_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "prompt": entry.get("prompt"),
        "count": int(entry.get("count") or 1),
        "last_used": entry.get("last_used"),
    }


def _collect_job_stats(limit: int = 5) -> List[Dict[str, Any]]:
    stats: List[Dict[str, Any]] = []
    for job in jobs_manager.list_jobs():
        success = int(job.get("success_count") or 0)
        failure = int(job.get("failure_count") or 0)
        total = success + failure
        if total == 0:
            continue
        rate = success / total if total else 0.0
        stats.append(
            {
                "id": job.get("id"),
                "type": job.get("type"),
                "description": job.get("description"),
                "tag": job.get("tag"),
                "success": success,
                "failure": failure,
                "success_rate": rate,
                "next_run": job.get("next_run"),
            }
        )
    stats.sort(key=lambda item: (item["success_rate"], item["success"], -item["failure"]), reverse=True)
    return stats[:limit]


def _suggest_chat_actions(limit: int = 5) -> List[Dict[str, Any]]:
    events = list_learning_events(limit=500)
    total_counter: Counter[str] = Counter()
    search_counter: Counter[str] = Counter()
    samples: Dict[str, str] = {}
    for event in events:
        if event.get("kind") != "chat_answer":
            continue
        payload = event.get("payload") or {}
        question = str(payload.get("question") or "").strip()
        if not question:
            continue
        normalized = " ".join(question.lower().split())
        samples.setdefault(normalized, question)
        total_counter[normalized] += 1
        if payload.get("used_search") and not payload.get("reused_memory"):
            search_counter[normalized] += 1
    suggestions: List[Dict[str, Any]] = []
    for key, occ in total_counter.most_common():
        if search_counter.get(key, 0) >= 2 and samples.get(key):
            suggestions.append(
                {
                    "question": samples[key],
                    "occurrences": occ,
                    "action": "Ajouter à la mémoire ou planifier un job dédié",
                    "reason": "Question répétée nécessitant une recherche web",
                }
            )
        if len(suggestions) >= limit:
            break
    return suggestions


async def record_feedback(
    *,
    question: str,
    answer: str,
    helpful: bool,
    qa_id: int | None,
    origin: str | None = None,
    note: str | None = None,
) -> None:
    """Persist a simple relevance feedback event."""
    payload = {
        "question": _trim_text(question, 512),
        "answer": _trim_text(answer, 800),
        "helpful": bool(helpful),
        "qa_id": qa_id,
        "origin": origin or "voice",
        "note": (note or "").strip(),
    }
    log_learning_event("voice_feedback", payload)
    if qa_id is not None:
        try:
            await chat_store.apply_feedback(qa_id, helpful=helpful, note=payload["note"])
        except Exception:
            pass


async def _hot_search_topics(limit: int = 5) -> list[dict[str, Any]]:
    await _ensure_table()
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                normalized_query,
                COUNT(*) AS occurrences,
                SUM(needs_search) AS needs_search_hits,
                MAX(created_at) AS last_seen
            FROM learning_events
            WHERE normalized_query IS NOT NULL
              AND TRIM(normalized_query) <> ''
            GROUP BY normalized_query
            HAVING needs_search_hits >= 2
            ORDER BY needs_search_hits DESC, occurrences DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    topics: list[dict[str, Any]] = []
    for row in rows:
        topics.append(
            {
                "query": row["normalized_query"],
                "occurrences": int(row["occurrences"] or 0),
                "needs_search_hits": int(row["needs_search_hits"] or 0),
                "last_seen": row["last_seen"],
            }
        )
    return topics


async def build_learning_summary(limit_prompts: int = 5, limit_jobs: int = 5, query_limit: int = 10) -> dict:
    limit_prompts = max(1, min(limit_prompts, 25))
    limit_jobs = max(1, min(limit_jobs, 25))
    query_limit = max(1, min(query_limit, 25))
    recent_prompts = [_format_prompt_entry(item) for item in job_prompts.list_prompts("recent")[:limit_prompts]]
    favorite_prompts = [_format_prompt_entry(item) for item in job_prompts.list_prompts("favorites")[:limit_prompts]]
    job_stats = _collect_job_stats(limit_jobs)
    job_recommendations = await _hot_search_topics(limit_jobs)
    suggestions = _suggest_chat_actions(limit_prompts)
    recent_events_limit = min(query_limit * 2, 50)
    top_queries_data, unresolved_data, recent_data = await asyncio.gather(
        top_queries(query_limit),
        unresolved_queries(query_limit),
        recent_events(recent_events_limit),
    )
    return {
        "recent_prompts": recent_prompts,
        "favorite_prompts": favorite_prompts,
        "top_jobs": job_stats,
        "job_recommendations": job_recommendations,
        "suggestions": suggestions,
        "top_queries": top_queries_data,
        "unresolved_queries": unresolved_data,
        "recent_events": recent_data,
    }
