from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List

LEARNING_LOG = Path("app/data/learning_events.jsonl")
MAX_EVENTS = 1000


def _ensure_file() -> None:
    LEARNING_LOG.parent.mkdir(parents=True, exist_ok=True)
    if not LEARNING_LOG.exists():
        LEARNING_LOG.touch()


def log_learning_event(kind: str, payload: Dict[str, Any]) -> None:
    """Append an event (chat answer, job insight, etc.) to the local log."""
    try:
        _ensure_file()
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "kind": kind,
            "payload": payload,
        }
        with LEARNING_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _trim_events()
    except Exception:
        pass


def _trim_events() -> None:
    """Keep the JSONL file under MAX_EVENTS by trimming the oldest entries."""
    try:
        with LEARNING_LOG.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        if len(lines) <= MAX_EVENTS:
            return
        with LEARNING_LOG.open("w", encoding="utf-8") as handle:
            handle.writelines(lines[-MAX_EVENTS:])
    except Exception:
        pass


def list_learning_events(limit: int = 200) -> List[Dict[str, Any]]:
    """Return the latest learning events (most recent last)."""
    if not LEARNING_LOG.exists():
        return []
    events: Deque[Dict[str, Any]] = deque(maxlen=limit)
    try:
        with LEARNING_LOG.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return list(events)
