from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import sqlite3

import aiosqlite

from app.core.config import Settings


def _ensure_parent(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


@asynccontextmanager
async def open_db() -> AsyncIterator[aiosqlite.Connection]:
    """Ouvre la base SQLite configurée et active WAL."""
    settings = Settings()
    db_path = Path(settings.db_path)
    _ensure_parent(db_path)
    db = await aiosqlite.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    finally:
        await db.close()
