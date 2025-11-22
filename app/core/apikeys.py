from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from passlib.context import CryptContext


_PWD = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
_FILE = Path("app/data/apikeys.json")


@dataclass
class APIKey:
    id: str
    name: str
    hash: str
    created_at: str
    last_used_at: Optional[str]
    scopes: List[str]


def _normalize_scopes(scopes: Iterable[str] | None) -> List[str]:
    """Return a deduplicated, ordered list of scopes."""
    if not scopes:
        return []
    ordered: list[str] = []
    for scope in scopes:
        if not isinstance(scope, str):
            continue
        value = scope.strip()
        if not value or value in ordered:
            continue
        ordered.append(value)
    return ordered


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_all() -> List[APIKey]:
    try:
        raw = _FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except Exception:
        return []

    try:
        data = json.loads(raw)
    except Exception:
        return []

    items: List[APIKey] = []
    if not isinstance(data, list):
        return items

    for entry in data:
        if not isinstance(entry, dict):
            continue
        key_id = entry.get("id")
        key_hash = entry.get("hash")
        name = entry.get("name")
        created = entry.get("created_at")
        last_used = entry.get("last_used_at")
        if not key_id or not key_hash:
            continue
        items.append(
            APIKey(
                id=str(key_id),
                name=str(name) if name is not None else "",
                hash=str(key_hash),
                created_at=str(created) if created else _now_iso(),
                last_used_at=str(last_used) if isinstance(last_used, str) and last_used else None,
                scopes=_normalize_scopes(entry.get("scopes")),
            )
        )
    return items


def _save_all(items: List[APIKey]) -> None:
    """Save atomically to prevent partial writes. Not a full concurrency lock."""
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    payload = [asdict(x) for x in items]
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(_FILE)


def list_keys() -> List[dict]:
    return [{**asdict(x), "hash": "***"} for x in _load_all()]


def create_key(name: str, scopes: Optional[List[str]] = None) -> dict:
    normalized_scopes = _normalize_scopes(scopes or [])
    token = secrets.token_urlsafe(24)
    key = APIKey(
        id=str(uuid.uuid4()),
        name=name,
        hash=_PWD.hash(token),
        created_at=_now_iso(),
        last_used_at=None,
        scopes=normalized_scopes,
    )
    items = _load_all()
    items.append(key)
    _save_all(items)
    return {
        "id": key.id,
        "name": key.name,
        "key": token,
        "scopes": list(normalized_scopes),
        "created_at": key.created_at,
    }


def delete_key(key_id: str) -> bool:
    items = _load_all()
    new_items = [k for k in items if k.id != key_id]
    if len(new_items) == len(items):
        return False
    _save_all(new_items)
    return True


def verify_token(token: str, required_scopes: Optional[List[str]] = None) -> Optional[dict]:
    items = _load_all()
    required = set(_normalize_scopes(required_scopes)) if required_scopes else set()
    for item in items:
        try:
            if item.hash.startswith(("$2b$", "$2a$", "$2y$")):
                import bcrypt  # type: ignore

                if not bcrypt.checkpw(token.encode("utf-8"), item.hash.encode("utf-8")):
                    continue
            elif not _PWD.verify(token, item.hash):
                continue
        except Exception:
            continue
        if required and not required.issubset(set(item.scopes)):
            continue
        item.last_used_at = _now_iso()
        _save_all(items)
        return {"sub": f"api:{item.id}", "name": item.name, "scopes": list(item.scopes)}
    return None
