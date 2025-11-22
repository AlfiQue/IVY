from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.asr import ASRUnavailableError, get_asr_engine
from app.core.logger import get_logger
from app.core.security import require_jwt_or_api_key
from app.core.voice_log import summarize_voice_events, tail_voice_events

router = APIRouter(prefix="/voice", tags=["voice"])
logger = get_logger("voice.asr")

VOICE_LOG_PATH = Path("app/logs/voice.asr.jsonl")
VOICE_TIME_FMT = "%Y-%m-%d %H:%M:%S,%f"


def _log_voice_event(message: str, **extra: Any) -> None:
    entry = {"timestamp": datetime.utcnow().strftime(VOICE_TIME_FMT), "message": message}
    if extra:
        entry.update(extra)
    try:
        VOICE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with VOICE_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # pragma: no cover - logging best effort
        logger.debug("Unable to persist voice log entry", exc_info=True)


@router.get("/logs")
async def voice_logs(limit: int = Query(100, ge=10, le=1000), _: None = Depends(require_jwt_or_api_key)) -> dict:
    events = tail_voice_events(limit)
    metrics = summarize_voice_events(events)
    return {"events": events, "metrics": metrics}


def _decode_frame(payload: dict[str, Any]) -> bytes:
    data = payload.get("data")
    if not isinstance(data, str):
        return b""
    try:
        return base64.b64decode(data)
    except Exception:
        return b""


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket) -> None:
    """Handle microphone streaming from the voice client and return transcripts."""

    await websocket.accept()
    _log_voice_event("Voice stream opened", client=str(websocket.client))
    logger.info("Voice stream opened from %s", websocket.client)
    buffer = bytearray()
    sample_rate: Optional[int] = None
    frame_count = 0

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                _log_voice_event("Invalid JSON frame", raw=raw_message[:64])
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_json(
                        {
                            "type": "transcript",
                            "text": "[Erreur] message JSON invalide.",
                            "final": False,
                            "confidence": None,
                        }
                    )
                continue

            msg_type = payload.get("type")
            if msg_type == "frame":
                frame = _decode_frame(payload)
                if frame:
                    buffer.extend(frame)
                    frame_count += 1
                    sr = payload.get("sample_rate")
                    if isinstance(sr, int):
                        sample_rate = sr
            elif msg_type == "end":
                logger.info("Voice stream END marker after %d frames (%.2f KB)", frame_count, len(buffer) / 1024)
                _log_voice_event(
                    "Voice stream END marker",
                    frames=frame_count,
                    kilobytes=round(len(buffer) / 1024, 2),
                    sample_rate=sample_rate,
                )
                try:
                    engine = get_asr_engine()
                except ASRUnavailableError as exc:
                    _log_voice_event("ASR unavailable", error=str(exc))
                    if websocket.application_state == WebSocketState.CONNECTED:
                        await websocket.send_json(
                            {
                                "type": "transcript",
                                "text": f"[ASR indisponible] {exc}",
                                "final": True,
                                "confidence": None,
                            }
                        )
                else:
                    loop = asyncio.get_running_loop()
                    raw_bytes = bytes(buffer)
                    buffer.clear()
                    text, segments = await loop.run_in_executor(
                        None, engine.transcribe_pcm16, raw_bytes, sample_rate or 16_000
                    )
                    transcript = text.strip() or "[aucune transcription]"
                    logger.info("ASR final transcript (%s chars)", len(transcript))
                    _log_voice_event(
                        "ASR final transcript",
                        chars=len(transcript),
                        frames=frame_count,
                        sample_rate=sample_rate or 16_000,
                    )
                    if websocket.application_state == WebSocketState.CONNECTED:
                        await websocket.send_json(
                            {
                                "type": "transcript",
                                "text": transcript,
                                "final": True,
                                "confidence": None,
                                "segments": segments,
                            }
                    )

                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.close()
                break
    except WebSocketDisconnect:
        logger.info("Voice stream disconnected: %s", websocket.client)
        _log_voice_event("Voice stream disconnected", client=str(websocket.client))
    except Exception as exc:
        logger.exception("Voice stream error", exc)
        _log_voice_event("Voice stream error", error=str(exc))
    finally:
        if websocket.application_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass
        else:
            _log_voice_event("Voice stream closed")
