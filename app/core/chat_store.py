from __future__ import annotations

import json
from datetime import datetime, UTC
from typing import Any, Iterable

import aiosqlite
import numpy as np

import re
import unicodedata

from app.core.db import open_db

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    origin TEXT NOT NULL,
    is_variable INTEGER NOT NULL DEFAULT 0,
    metadata TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id DESC);

CREATE TABLE IF NOT EXISTS qa_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    is_variable INTEGER NOT NULL DEFAULT 0,
    origin TEXT NOT NULL DEFAULT 'database',
    embedding BLOB,
    embedding_dim INTEGER,
    metadata TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    last_used TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_qa_question ON qa_entries(question);

CREATE VIRTUAL TABLE IF NOT EXISTS qa_entries_fts USING fts5(
    question,
    answer,
    content='qa_entries',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS qa_entries_ai AFTER INSERT ON qa_entries BEGIN
    INSERT INTO qa_entries_fts(rowid, question, answer) VALUES (new.id, new.question, new.answer);
END;
CREATE TRIGGER IF NOT EXISTS qa_entries_ad AFTER DELETE ON qa_entries BEGIN
    INSERT INTO qa_entries_fts(qa_entries_fts, rowid, question, answer) VALUES ('delete', old.id, old.question, old.answer);
END;
CREATE TRIGGER IF NOT EXISTS qa_entries_au AFTER UPDATE ON qa_entries BEGIN
    INSERT INTO qa_entries_fts(qa_entries_fts, rowid, question, answer) VALUES ('delete', old.id, old.question, old.answer);
    INSERT INTO qa_entries_fts(rowid, question, answer) VALUES (new.id, new.question, new.answer);
END;
"""


async def init_db() -> None:
    async with open_db() as db:
        await db.executescript(_SCHEMA)
        await db.commit()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _dump_metadata(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return None


def _load_metadata(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def create_conversation(title: str | None = None) -> dict[str, Any]:
    async with open_db() as db:
        cursor = await db.execute(
            "INSERT INTO conversations(title, created_at, updated_at) VALUES (?, ?, ?)",
            (title, _now_iso(), _now_iso()),
        )
        await db.commit()
        conv_id = cursor.lastrowid
    return await get_conversation(conv_id)


async def touch_conversation(conv_id: int) -> None:
    async with open_db() as db:
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now_iso(), conv_id),
        )
        await db.commit()


async def ensure_conversation(conv_id: int | None, *, title: str | None = None) -> dict[str, Any]:
    if conv_id is None:
        return await create_conversation(title)
    existing = await get_conversation(conv_id)
    if existing is None:
        return await create_conversation(title)
    return existing


async def get_conversation(conv_id: int) -> dict[str, Any] | None:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (conv_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return dict(row)


async def list_conversations(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) AS last_message
            FROM conversations AS c
            ORDER BY c.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def add_message(
    conversation_id: int,
    *,
    role: str,
    content: str,
    origin: str,
    is_variable: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta_dump = _dump_metadata(metadata)
    async with open_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO messages(conversation_id, role, content, origin, is_variable, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                origin,
                1 if is_variable else 0,
                meta_dump,
                _now_iso(),
            ),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now_iso(), conversation_id),
        )
        await db.commit()
        msg_id = cursor.lastrowid
    return await get_message(msg_id)


async def get_message(message_id: int) -> dict[str, Any] | None:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, conversation_id, role, content, origin, is_variable, metadata, created_at FROM messages WHERE id = ?",
            (message_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    data = dict(row)
    data["is_variable"] = bool(data.get("is_variable"))
    data["metadata"] = _load_metadata(data.get("metadata"))
    return data


async def list_messages(conversation_id: int, limit: int = 100, before_id: int | None = None) -> list[dict[str, Any]]:
    where = ["conversation_id = ?"]
    params: list[Any] = [conversation_id]
    if before_id is not None:
        where.append("id < ?")
        params.append(before_id)
    clause = " AND ".join(where)
    query = (
        "SELECT id, conversation_id, role, content, origin, is_variable, metadata, created_at "
        "FROM messages WHERE " + clause + " ORDER BY id DESC LIMIT ?"
    )
    params.append(limit)
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
    items = []
    for row in rows:
        data = dict(row)
        data["is_variable"] = bool(data.get("is_variable"))
        data["metadata"] = _load_metadata(data.get("metadata"))
        items.append(data)
    return list(reversed(items))


async def save_qa(
    *,
    question: str,
    answer: str,
    is_variable: bool,
    origin: str,
    embedding: np.ndarray | None,
    metadata: dict[str, Any] | None = None,
) -> int:
    meta_dump = _dump_metadata(metadata)
    blob = embedding.tobytes() if embedding is not None else None
    dim = int(embedding.shape[0]) if embedding is not None else None
    now = _now_iso()
    async with open_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO qa_entries(question, answer, is_variable, origin, embedding, embedding_dim, metadata, usage_count, last_used, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
            """,
            (
                question,
                answer,
                1 if is_variable else 0,
                origin,
                blob,
                dim,
                meta_dump,
                now,
                now,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def update_qa(qa_id: int, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return await get_qa(qa_id)
    allowed = {"question", "answer", "is_variable", "origin", "metadata", "embedding"}
    updates: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "metadata":
            updates.append("metadata = ?")
            params.append(_dump_metadata(value))
        elif key == "is_variable":
            updates.append("is_variable = ?")
            params.append(1 if bool(value) else 0)
        elif key == "embedding":
            if value is None:
                updates.append("embedding = ?")
                params.append(None)
                updates.append("embedding_dim = ?")
                params.append(None)
            elif isinstance(value, np.ndarray):
                updates.append("embedding = ?")
                params.append(value.tobytes())
                updates.append("embedding_dim = ?")
                params.append(int(value.shape[0]))
        else:
            updates.append(f"{key} = ?")
            params.append(value)
    if not updates:
        return await get_qa(qa_id)
    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(qa_id)
    async with open_db() as db:
        await db.execute(
            "UPDATE qa_entries SET " + ", ".join(updates) + " WHERE id = ?",
            params,
        )
        await db.commit()
    return await get_qa(qa_id)


async def get_qa(qa_id: int) -> dict[str, Any] | None:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, question, answer, is_variable, origin, embedding, embedding_dim, metadata, usage_count, last_used, created_at, updated_at FROM qa_entries WHERE id = ?",
            (qa_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    data = dict(row)
    data["is_variable"] = bool(data.get("is_variable"))
    data["metadata"] = _load_metadata(data.get("metadata"))
    return data




def _tokenize_search_terms(value: str) -> list[str]:
    return [token for token in re.split(r"\s+", value.strip()) if token]


def _strip_diacritics(value: str) -> str:
    normalized = unicodedata.normalize('NFD', value)
    return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')


def _escape_like_token(value: str) -> str:
    return value.replace('\\', '\\').replace('%', r'\%').replace('_', r'\_')


def _build_fts_query(tokens: list[str]) -> str | None:
    parts: list[str] = []
    for token in tokens:
        cleaned = re.sub(r"[\"'`]+", "", token)
        if cleaned:
            parts.append(f"{cleaned}*")
    return ' OR '.join(parts) if parts else None


async def list_qa(limit: int = 100, offset: int = 0, search: str | None = None) -> dict[str, Any]:
    tokens = _tokenize_search_terms(search) if search else []
    unique_tokens: list[str] = []
    seen_tokens: set[str] = set()
    for token in tokens:
        if token not in seen_tokens:
            seen_tokens.add(token)
            unique_tokens.append(token)
    additional = []
    for token in unique_tokens:
        stripped = _strip_diacritics(token)
        if stripped and stripped not in seen_tokens:
            seen_tokens.add(stripped)
            additional.append(stripped)
    like_tokens = unique_tokens + additional

    criteria: list[str] = []
    params: list[Any] = []

    fts_query = _build_fts_query(unique_tokens)
    if fts_query:
        criteria.append("rowid IN (SELECT rowid FROM qa_entries_fts WHERE qa_entries_fts MATCH ?)")
        params.append(fts_query)

    if like_tokens:
        like_fragments: list[str] = []
        like_params: list[str] = []
        for token in like_tokens:
            escaped = _escape_like_token(token)
            pattern = f"%{escaped}%"
            like_fragments.append("(question LIKE ? ESCAPE '\\' OR answer LIKE ? ESCAPE '\\')")
            like_params.extend([pattern, pattern])
        if like_fragments:
            criteria.append("(" + " AND ".join(like_fragments) + ")")
            params.extend(like_params)

    clause = f" WHERE {' OR '.join(criteria)}" if criteria else ""
    query = (
        "SELECT id, question, answer, is_variable, origin, metadata, usage_count, last_used, created_at, updated_at "
        "FROM qa_entries" + clause + " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    )
    params_for_query = params + [limit, offset]

    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params_for_query) as cur:
            rows = await cur.fetchall()
        async with db.execute("SELECT COUNT(*) FROM qa_entries" + clause, params) as cur:
            total_row = await cur.fetchone()

    items = []
    for row in rows:
        data = dict(row)
        data['is_variable'] = bool(data.get('is_variable'))
        data['metadata'] = _load_metadata(data.get('metadata'))
        items.append(data)
    total = total_row[0] if total_row else 0
    return {'items': items, 'total': total}



async def delete_qa(qa_id: int) -> None:
    async with open_db() as db:
        await db.execute("DELETE FROM qa_entries WHERE id = ?", (qa_id,))
        await db.commit()


async def record_usage(qa_id: int) -> None:
    async with open_db() as db:
        await db.execute(
            "UPDATE qa_entries SET usage_count = usage_count + 1, last_used = ?, updated_at = ? WHERE id = ?",
            (_now_iso(), _now_iso(), qa_id),
        )
        await db.commit()


async def load_embeddings() -> list[tuple[int, np.ndarray, bool, str, str]]:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, question, answer, embedding, embedding_dim, is_variable, origin FROM qa_entries WHERE embedding IS NOT NULL",
        ) as cur:
            rows = await cur.fetchall()
    results: list[tuple[int, np.ndarray, bool, str, str]] = []
    for row in rows:
        blob = row["embedding"]
        dim = row["embedding_dim"]
        if blob is None or dim is None:
            continue
        try:
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.shape[0] != dim:
                continue
            vec = vec.reshape(-1)
        except Exception:
            continue
        results.append((row["id"], vec, bool(row["is_variable"]), row["question"], row["answer"]))
    return results


async def similar_questions(vector: np.ndarray, limit: int = 5) -> list[dict[str, Any]]:
    entries = await load_embeddings()
    if not entries:
        return []
    matrix = np.stack([item[1] for item in entries], axis=0)
    scores = matrix @ vector.reshape(-1)
    ordered = np.argsort(-scores)
    results: list[dict[str, Any]] = []
    for idx in ordered[:limit]:
        qa_id, vec, is_var, question, answer = entries[idx]
        score = float(scores[idx])
        results.append(
            {
                "id": qa_id,
                "similarity": score,
                "question": question,
                "answer": answer,
                "is_variable": is_var,
            }
        )
    return results


async def import_qa(entries: Iterable[dict[str, Any]]) -> dict[str, int]:
    created = 0
    skipped = 0
    async with open_db() as db:
        for item in entries:
            question = item.get("question")
            answer = item.get("answer")
            if not question or not answer:
                skipped += 1
                continue
            is_variable = bool(item.get("is_variable", False))
            origin = item.get("origin") or "import"
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else None
            embedding_blob = item.get("embedding")
            embedding_dim = item.get("embedding_dim")
            await db.execute(
                """
                INSERT INTO qa_entries(question, answer, is_variable, origin, embedding, embedding_dim, metadata, usage_count, last_used, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question,
                    answer,
                    1 if is_variable else 0,
                    origin,
                    embedding_blob,
                    embedding_dim,
                    _dump_metadata(metadata),
                    int(item.get("usage_count") or 0),
                    item.get("last_used"),
                    item.get("created_at") or _now_iso(),
                    item.get("updated_at") or _now_iso(),
                ),
            )
            created += 1
        await db.commit()
    return {"created": created, "skipped": skipped}


async def export_qa() -> list[dict[str, Any]]:
    async with open_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, question, answer, is_variable, origin, embedding, embedding_dim, metadata, usage_count, last_used, created_at, updated_at FROM qa_entries ORDER BY updated_at DESC",
        ) as cur:
            rows = await cur.fetchall()
    items = []
    for row in rows:
        data = dict(row)
        data["is_variable"] = bool(data.get("is_variable"))
        meta = _load_metadata(data.get("metadata"))
        data["metadata"] = meta
        items.append(data)
    return items


async def count_conversations() -> int:
    async with open_db() as db:
        async with db.execute("SELECT COUNT(*) FROM conversations") as cur:
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def clear_all() -> None:
    async with open_db() as db:
        for stmt in (
            "DELETE FROM messages",
            "DELETE FROM conversations",
            "DELETE FROM qa_entries",
            "DELETE FROM qa_entries_fts",
        ):
            try:
                await db.execute(stmt)
            except Exception:
                pass
        await db.commit()
    await init_db()

async def rename_conversation(conv_id: int, title: str | None) -> dict[str, Any] | None:
    async with open_db() as db:
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now_iso(), conv_id),
        )
        await db.commit()
    return await get_conversation(conv_id)


async def delete_conversation(conv_id: int) -> None:
    async with open_db() as db:
        await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await db.commit()

async def count_qa() -> int:
    async with open_db() as db:
        async with db.execute("SELECT COUNT(*) FROM qa_entries") as cur:
            row = await cur.fetchone()
    return int(row[0]) if row else 0

