from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal


STORE_PATH = Path("app/data/job_prompts.json")
MAX_RECENT = 15
MAX_FAVORITES = 30


def _default_store() -> dict[str, list[dict[str, object]]]:
    return {"recent": [], "favorites": []}


def _load_store() -> dict[str, list[dict[str, object]]]:
    if not STORE_PATH.exists():
        return _default_store()
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            recent = data.get("recent")
            favorites = data.get("favorites")
            return {
                "recent": recent if isinstance(recent, list) else [],
                "favorites": favorites if isinstance(favorites, list) else [],
            }
    except Exception:
        pass
    return _default_store()


def _save_store(data: dict[str, list[dict[str, object]]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_prompts(kind: Literal["recent", "favorites"]) -> list[dict[str, object]]:
    store = _load_store()
    items = store.get(kind, [])
    try:
        return sorted(items, key=lambda item: item.get("last_used", ""), reverse=True)
    except Exception:
        return items


def save_prompt(prompt: str, *, favorite: bool = False) -> dict[str, object]:
    text = (prompt or "").strip()
    if not text:
        raise ValueError("prompt vide")
    store = _load_store()
    category = "favorites" if favorite else "recent"
    target = store.get(category, [])
    now = datetime.utcnow().isoformat()
    updated = False
    for entry in target:
        if entry.get("prompt") == text:
            entry["last_used"] = now
            entry["count"] = int(entry.get("count", 1)) + 1
            updated = True
            break
    if not updated:
        target.insert(0, {"prompt": text, "last_used": now, "count": 1})
    limit = MAX_FAVORITES if category == "favorites" else MAX_RECENT
    store[category] = target[:limit]
    _save_store(store)
    return {"prompt": text, "last_used": now}
