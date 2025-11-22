"""Gestion de l'historique des événements."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite
import sqlite3

from .config import Settings

__all__ = [
    "insert_event",
    "list_events",
    "ping_db",
    "search_events",
    "get_event",
    "clear_events",
    "log_event",
    "log_event_sync",
]


def _get_db_path() -> Path:
    """Retourne le chemin vers la base SQLite."""
    settings = Settings()
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@asynccontextmanager
async def _open_db() -> aiosqlite.Connection:
    """Ouvre la base de données et active le mode WAL."""
    db = await aiosqlite.connect(_get_db_path())
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    try:
        yield db
    finally:
        await db.close()


async def ping_db() -> bool:
    """Vérifie que la base de données est accessible."""
    try:
        async with _open_db() as db:
            await db.execute("SELECT 1")
        return True
    except Exception:
        return False


async def insert_event(event_type: str, payload: Any) -> int:
    """Insère un événement et retourne son identifiant."""
    settings = Settings()
    patterns = [p.strip().lower() for p in (settings.mask_secrets_patterns or "").split(",") if p.strip()]

    def _mask(obj: Any) -> Any:
        try:
            if isinstance(obj, dict):
                out: dict[str, Any] = {}
                for k, v in obj.items():
                    if any(p in str(k).lower() for p in patterns):
                        out[k] = "***"
                    else:
                        out[k] = _mask(v)
                return out
            if isinstance(obj, list):
                return [_mask(x) for x in obj]
            return obj
        except Exception:
            return obj

    masked = _mask(payload) if not isinstance(payload, str) else payload
    data = json.dumps(masked) if not isinstance(masked, str) else masked
    async with _open_db() as db:
        cursor = await db.execute(
            "INSERT INTO events(type, payload) VALUES (?, ?)", (event_type, data)
        )
        await db.commit()
        rowid = cursor.lastrowid
    try:
        await _purge()
    except Exception:
        pass
    return rowid


async def log_event(event_type: str, payload: Any) -> int | None:
    """Enregistre un événement en ignorant silencieusement les erreurs."""
    try:
        return await insert_event(event_type, payload)
    except Exception:
        return None


def log_event_sync(event_type: str, payload: Any) -> None:
    """Version synchrone à utiliser hors contexte asyncio."""

    async def _runner() -> None:
        await log_event(event_type, payload)

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


async def list_events(limit: int) -> list[dict[str, Any]]:
    """Retourne les ``limit`` derniers événements."""
    async with _open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, type, payload, created_at FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item["payload"])
        except Exception:
            pass
        events.append(item)
    return events


async def search_events(
    *,
    limit: int = 20,
    offset: int = 0,
    q: str | None = None,
    plugin: str | None = None,
    start: str | None = None,
    end: str | None = None,
    event_type: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Recherche paginée dans les événements avec filtres simples.

    Les filtres ``q`` et ``plugin`` opèrent sur le champ ``payload`` (texte JSON) côté SQLite.
    Les bornes ``start`` et ``end`` filtrent sur ``created_at`` (format ISO recommandé).
    """
    where: list[str] = []
    params: list[Any] = []
    if q:
        where.append("payload LIKE ?")
        params.append(f"%{q}%")
    if plugin:
        where.append("payload LIKE ?")
        params.append(f"%\"{plugin}\"%")
    if event_type:
        where.append("type = ?")
        params.append(event_type)
    if session_id:
        where.append("payload LIKE ?")
        params.append(f"%\"session_id\"%:%\"{session_id}\"%")
    if start:
        where.append("created_at >= ?")
        params.append(start)
    if end:
        where.append("created_at <= ?")
        params.append(end)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    async with _open_db() as db:
        db.row_factory = aiosqlite.Row
        # total
        async with db.execute(f"SELECT COUNT(*) AS c FROM events{clause}", params) as cur:
            row = await cur.fetchone()
            total = int(row["c"]) if row else 0
        # page
        async with db.execute(
            f"SELECT id, type, payload, created_at FROM events{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ) as cur:
            rows = await cur.fetchall()
    items: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d["payload"])
        except Exception:
            pass
        items.append(d)
    return {"items": items, "total": total}


async def get_event(event_id: int) -> dict[str, Any] | None:
    async with _open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, type, payload, created_at FROM events WHERE id = ?",
            (event_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["payload"] = json.loads(d["payload"])
    except Exception:
        pass
    return d


async def clear_events() -> None:
    """Supprime l'historique tout en gérant un éventuel verrou SQLite."""
    for attempt in range(3):
        try:
            async with _open_db() as db:
                await db.execute("DELETE FROM events")
                await db.commit()
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 2:
                raise
            await asyncio.sleep(0.2 * (attempt + 1))


async def _purge() -> None:
    settings = Settings()
    db_path = Path(settings.db_path)
    size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0
    async with _open_db() as db:
        if settings.history_retention_days > 0:
            await db.execute(
                "DELETE FROM events WHERE datetime(created_at) < datetime('now', ?)",
                (f"-{int(settings.history_retention_days)} days",),
            )
            await db.commit()
        if size_mb > settings.history_max_mb:
            await db.execute(
                "DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY id ASC LIMIT (SELECT COUNT(*)/10 FROM events))"
            )
            await db.commit()
