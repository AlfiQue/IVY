from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, List, Dict

import aiosqlite

from app.core.db import open_db

_INIT_LOCK = asyncio.Lock()
_TABLE_READY = False
_PROMPT_MAX_LEN = 2000


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
                CREATE TABLE IF NOT EXISTS job_prompts (
                    prompt TEXT PRIMARY KEY,
                    usage_count INTEGER NOT NULL DEFAULT 1,
                    last_used TEXT NOT NULL
                )
                """
            )
            await db.commit()
        _TABLE_READY = True


def _sanitize_prompt(prompt: str) -> str:
    text = (prompt or "").strip()
    if not text:
        return ""
    if len(text) > _PROMPT_MAX_LEN:
        text = text[:_PROMPT_MAX_LEN]
    return text


async def record_prompt(prompt: str) -> None:
    text = _sanitize_prompt(prompt)
    if not text:
        return
    await _ensure_table()
    now = datetime.now(timezone.utc).isoformat()
    async with open_db() as db:
        await db.execute(
            """
            INSERT INTO job_prompts(prompt, usage_count, last_used)
            VALUES (?, 1, ?)
            ON CONFLICT(prompt) DO UPDATE SET
                usage_count = usage_count + 1,
                last_used = excluded.last_used
            """,
            (text, now),
        )
        await db.commit()


def record_prompt_sync(prompt: str) -> None:
    async def _runner() -> None:
        await record_prompt(prompt)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(_runner())
        except Exception:
            pass
        return

    try:
        loop.create_task(_runner())
    except RuntimeError:
        try:
            asyncio.run(_runner())
        except Exception:
            pass


async def list_recent(limit: int = 10) -> List[Dict[str, Any]]:
    await _ensure_table()
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT prompt, usage_count, last_used
            FROM job_prompts
            ORDER BY datetime(last_used) DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def list_top(limit: int = 10) -> List[Dict[str, Any]]:
    await _ensure_table()
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT prompt, usage_count, last_used
            FROM job_prompts
            ORDER BY usage_count DESC, datetime(last_used) DESC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]

