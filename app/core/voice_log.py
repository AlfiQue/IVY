from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


VOICE_LOG_PATH = Path("app/logs/voice.asr.jsonl")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S,%f"


def _parse_timestamp(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except Exception:
        return None


def tail_voice_events(limit: int = 200) -> List[Dict[str, Any]]:
    if not VOICE_LOG_PATH.exists():
        return []
    events: Deque[Dict[str, Any]] = deque(maxlen=limit)
    try:
        with VOICE_LOG_PATH.open("r", encoding="utf-8") as handle:
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


def summarize_voice_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "total_events": len(events),
        "streams_opened": 0,
        "streams_completed": 0,
        "recording_durations_ms": [],
        "post_process_latencies_ms": [],
    }
    last_open_time: Optional[datetime] = None
    last_end_time: Optional[datetime] = None
    for event in events:
        ts = _parse_timestamp(str(event.get("timestamp", "")))
        message = str(event.get("message", ""))
        if "Voice stream opened" in message:
            metrics["streams_opened"] += 1
            last_open_time = ts
        elif "END marker" in message:
            metrics["streams_completed"] += 1
            if ts and last_open_time:
                delta = (ts - last_open_time).total_seconds() * 1000
                metrics["recording_durations_ms"].append(delta)
            last_end_time = ts
            last_open_time = None
        elif "ASR final transcript" in message:
            if ts and last_end_time:
                delta = (ts - last_end_time).total_seconds() * 1000
                metrics["post_process_latencies_ms"].append(delta)
            last_end_time = None

    def _avg(values: List[float]) -> Optional[float]:
        return sum(values) / len(values) if values else None

    def _p95(values: List[float]) -> Optional[float]:
        if not values:
            return None
        sorted_vals = sorted(values)
        k = int(0.95 * (len(sorted_vals) - 1))
        return sorted_vals[k]

    metrics["avg_recording_ms"] = _avg(metrics["recording_durations_ms"])
    metrics["p95_recording_ms"] = _p95(metrics["recording_durations_ms"])
    metrics["avg_post_process_ms"] = _avg(metrics["post_process_latencies_ms"])
    metrics["p95_post_process_ms"] = _p95(metrics["post_process_latencies_ms"])
    if metrics["recording_durations_ms"]:
        metrics["max_recording_ms"] = max(metrics["recording_durations_ms"])
    if metrics["post_process_latencies_ms"]:
        metrics["max_post_process_ms"] = max(metrics["post_process_latencies_ms"])
    metrics["stalled_streams"] = max(
        0,
        metrics["streams_opened"] - metrics["streams_completed"],
    )
    return metrics
