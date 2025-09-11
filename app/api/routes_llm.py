from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import ValidationError

from app.core.llm import LLM
from app.core.config import Settings
from app.core.plugins import PluginError
from app.core.ws import close_connection, send_error, send_token
from app.core.security import verify_jwt
from app.core.errors import error_response
from app.core.trace import get_trace_id
from app.core.metrics import inc_llm_tokens

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/infer")
async def infer_llm(data: dict) -> dict:
    """Retourne la rÃ©ponse complÃ¨te du LLM."""
    prompt = data.get("prompt")
    options = data.get("options") or {}
    if prompt is None:
        raise HTTPException(status_code=400, detail="Champ 'prompt' manquant")
    settings = Settings()
    if len(str(prompt)) > settings.llm_max_input_tokens * 4:
        got_est = len(str(prompt)) // 4
        msg = f"Input too large (max {settings.llm_max_input_tokens} tokens)."
        raise HTTPException(
            status_code=400,
            detail=error_response(
                "IVY_4101",
                msg,
                details={"limit": settings.llm_max_input_tokens, "got": got_est},
                trace_id=get_trace_id(),
            ),
        )
    model_path = os.environ.get("LLM_MODEL_PATH")
    if model_path is None:
        raise HTTPException(status_code=500, detail="ModÃ¨le non configurÃ©")
    llm = LLM(model_path)
    try:
        # forcer limite max_tokens
        options.setdefault("max_tokens", settings.llm_max_output_tokens)
        text = await asyncio.to_thread(llm.infer, prompt, options)
    except (ValidationError, PluginError) as exc:
        raise HTTPException(status_code=400, detail=error_response("IVY_4102","invalid request", details=str(exc), trace_id=get_trace_id())) from exc
    return {"text": text}


@router.websocket("/stream")
async def stream_llm(websocket: WebSocket) -> None:
    """Diffuse les tokens gÃ©nÃ©rÃ©s par le LLM via WebSocket."""
    await websocket.accept()
    try:
        # Auth par cookie JWT (si fourni). Si absent, configurable via ws_auth_required
        cookies = websocket.headers.get("cookie") or ""
        token = None
        for part in cookies.split(";"):
            if part.strip().startswith("access_token="):
                token = part.strip().split("=", 1)[1]
                break
        if token and not verify_jwt(token).get("sub"):
            await send_error(websocket, None, "llm", "unauthorized", code="IVY_4010")
            await websocket.close(code=1008)
            return
        if Settings().ws_auth_required and not token:
            await send_error(websocket, None, "llm", "unauthorized", code="IVY_4010")
            await websocket.close(code=1008)
            return
        data = await websocket.receive_json()
        payload = data.get("payload") or {}
        prompt = payload.get("prompt")
        options = payload.get("options") or {}
        req_id = data.get("req_id")
        model_path = os.environ.get("LLM_MODEL_PATH")
        if model_path is None or prompt is None:
            await send_error(websocket, req_id, "llm", "missing model or prompt", code="IVY_4100")
            await websocket.close(code=1008)
            return
        settings = Settings()
        if len(str(prompt)) > settings.llm_max_input_tokens * 4:
            got_est = len(str(prompt)) // 4
            await send_error(
                websocket,
                req_id,
                "llm",
                f"Input too large (max {settings.llm_max_input_tokens} tokens).",
                code="IVY_4101",
                details={"limit": settings.llm_max_input_tokens, "got": got_est},
            )
            await websocket.close(code=1008)
            return
        llm = LLM(model_path)

        # Heartbeat (ping/pong)
        interval = max(5, Settings().ws_heartbeat_sec)
        last_pong = asyncio.get_event_loop().time()

        async def _recv_pong() -> None:
            nonlocal last_pong
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.receive_json(), timeout=interval)
                    # tout message reÃ§u rÃ©initialise le timer; si "event":"pong", rien d'autre Ã  faire
                    last_pong = asyncio.get_event_loop().time()
                except asyncio.TimeoutError:
                    # vÃ©rifier inactivitÃ© > 2x interval
                    if asyncio.get_event_loop().time() - last_pong > 2 * interval:
                        await send_error(websocket, req_id, "llm", "heartbeat timeout", code="IVY_4000")
                        await websocket.close(code=1011)
                        return
                except Exception:
                    return

        async def _stream_tokens() -> None:
            async for tok in llm.astream(prompt, options):
                await send_token(websocket, req_id, "llm", tok)
                try:
                    inc_llm_tokens(1)
                except Exception:
                    pass
            await close_connection(websocket, req_id, "llm")

        async def _send_ping() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    # ping applicatif via statut
                    from app.core.ws import send_status

                    await send_status(websocket, req_id, "ping")
                except Exception:
                    return

        recv_task = asyncio.create_task(_recv_pong())
        ping_task = asyncio.create_task(_send_ping())
        try:
            await _stream_tokens()
        finally:
            recv_task.cancel()
            ping_task.cancel()
    except Exception as exc:
        await send_error(websocket, req_id, "llm", str(exc), code="IVY_5000")
        await websocket.close(code=1011)


