"""HTTP and WebSocket client used to talk to IVY."""

from __future__ import annotations

import asyncio
import contextlib
import base64
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Optional

import httpx
from websockets.client import connect as ws_connect

from ..config.settings import AppSettings
from ..utils.dpapi import unprotect
from .schemas import ChatMessage, SystemCommand, TranscriptEvent


@dataclass(slots=True)
class AuthTokens:
    """Authentication tokens returned by IVY."""

    access_token: str | None
    csrf_token: str | None
    session_id: str | None = None


class IvyAPI:
    """Async client for IVY."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        timeout = httpx.Timeout(
            connect=30.0,
            read=180.0,
            write=30.0,
            pool=None,
        )
        self._client = httpx.AsyncClient(
            base_url=settings.server.base_url,
            verify=settings.server.verify_ssl,
            timeout=timeout,
        )
        self._tokens: AuthTokens | None = None
        self._authenticated = False
        self._last_chat_meta: dict[str, Any] = {}

    async def login(self) -> None:
        """Authenticate against IVY and store tokens."""
        password = self._resolve_password()
        response = await self._client.post(
            "/auth/login",
            json={
                "user": self.settings.server.username,
                "password": password,
            },
        )
        response.raise_for_status()
        data = response.json()
        cookies = response.cookies or {}
        self._tokens = AuthTokens(
            access_token=cookies.get("access_token"),
            csrf_token=data.get("csrf_token"),
            session_id=cookies.get("session_id") or data.get("session_id"),
        )
        if not self._tokens.access_token:
            raise RuntimeError("access_token absent du cookie de réponse.")
        self._authenticated = True

    async def stream_voice(self, iterator: AsyncIterator[bytes], sample_rate: int) -> AsyncIterator[TranscriptEvent]:
        """Send audio frames and receive partial transcriptions."""
        base = self.settings.server.base_url.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://") :]
        else:
            ws_base = base
        url = ws_base + "/voice/stream"
        headers_list: list[tuple[str, str]] = []
        if self._tokens:
            cookie_parts: list[str] = []
            if self._tokens.access_token:
                headers_list.append(("Authorization", f"Bearer {self._tokens.access_token}"))
                cookie_parts.append(f"access_token={self._tokens.access_token}")
            if self._tokens.session_id:
                cookie_parts.append(f"session_id={self._tokens.session_id}")
            if cookie_parts:
                headers_list.append(("Cookie", "; ".join(cookie_parts)))
            if self._tokens.csrf_token:
                headers_list.append(("X-CSRF-Token", self._tokens.csrf_token))

        async with ws_connect(url, extra_headers=headers_list or None) as websocket:
            event_queue: asyncio.Queue[Any] = asyncio.Queue()

            async def receiver() -> None:
                try:
                    async for message in websocket:
                        event = self._parse_transcript(message)
                        if event:
                            await event_queue.put(event)
                except Exception as exc:
                    await event_queue.put(exc)
                finally:
                    await event_queue.put(None)

            receiver_task = asyncio.create_task(receiver())

            try:
                async for chunk in iterator:
                    payload = {
                        "type": "frame",
                        "format": "pcm_s16le",
                        "sample_rate": sample_rate,
                        "data": base64.b64encode(chunk).decode("ascii"),
                    }
                    await websocket.send(json.dumps(payload))

                await websocket.send(json.dumps({"type": "end"}))

                while True:
                    item = await event_queue.get()
                    if item is None:
                        break
                    if isinstance(item, Exception):
                        raise item
                    yield item
            finally:
                receiver_task.cancel()
                with contextlib.suppress(Exception):
                    await receiver_task
    async def send_chat(self, message: ChatMessage) -> AsyncIterator[str]:
        """Send a chat message and stream the assistant response."""
        if not self._authenticated or self._tokens is None:
            raise RuntimeError("Client non authentifie. Connectez-vous avant d'envoyer un message.")

        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}
        token = self._tokens.access_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
            cookies["access_token"] = token
        if self._tokens.csrf_token:
            headers["X-CSRF-Token"] = self._tokens.csrf_token
        if self._tokens.session_id:
            cookies["session_id"] = self._tokens.session_id

        payload: dict[str, Any] = {"question": message.content}
        conversation_id = message.metadata.get("conversation_id")
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        user = message.metadata.get("user")
        if user:
            payload["user"] = user
        if "use_speculative" in message.metadata:
            payload["use_speculative"] = bool(message.metadata["use_speculative"])
        payload["response_mode"] = "voice_concise"

        try:
            response = await self._client.post(
                "/chat/query",
                json=payload,
                headers=headers or None,
                cookies=cookies or None,
            )
        except httpx.ReadTimeout as exc:
            raise RuntimeError("Timeout de lecture lors de la reponse du LLM.") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("Timeout de connexion avec le serveur IVY.") from exc
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            snippet = response.text[:200]
            raise RuntimeError(f"Reponse non-JSON du serveur: {snippet}") from exc
        self._last_chat_meta = data if isinstance(data, dict) else {}
        answer = ""
        if isinstance(data, dict):
            raw_answer = data.get("answer", "")
            answer = raw_answer if isinstance(raw_answer, str) else str(raw_answer)
        yield answer

    async def send_feedback(
        self,
        *,
        qa_id: int,
        question: str,
        answer: str,
        helpful: bool,
        origin: str = "voice",
        comment: str | None = None,
    ) -> None:
        """Send a relevance feedback signal to the learning API."""
        payload = {
            "qa_id": qa_id,
            "question": question,
            "answer": answer,
            "helpful": bool(helpful),
            "origin": origin,
            "comment": comment,
        }
        await self._client.post("/learning/feedback", json=payload)

    async def execute_command(
        self,
        command: SystemCommand,
        *,
        status: str = "accepted",
        note: str | None = None,
    ) -> None:
        """Confirm command execution to the backend."""
        payload = {
            "status": status,
            "note": note,
            **command.to_payload(),
        }
        await self._client.post("/commands/ack", json=payload)

    async def report_command(self, command: SystemCommand, *, note: str | None = None) -> None:
        """Send a command suggestion for learning."""
        payload = {"command": command.to_payload()}
        if note:
            payload["note"] = note
        await self._client.post("/commands/report", json=payload)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
        self._authenticated = False

    @property
    def is_authenticated(self) -> bool:
        """Return True if login succeeded."""
        return self._authenticated

    @property
    def last_chat_metadata(self) -> dict[str, Any]:
        """Return the metadata of the last chat response."""
        return self._last_chat_meta

    @property
    def last_conversation_id(self) -> Optional[int]:
        """Return the last conversation identifier if available."""
        value = self._last_chat_meta.get("conversation_id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _resolve_password(self) -> str:
        """Return the password using DPAPI unprotect if needed."""
        server = self.settings.server
        if server.password_plaintext:
            return server.password_plaintext
        if server.password_encrypted:
            try:
                return unprotect(server.password_encrypted).decode("utf-8")
            except Exception as exc:
                server.password_encrypted = None
                raise RuntimeError("Impossible de dechiffrer le mot de passe enregistre.") from exc
        raise RuntimeError("Aucun mot de passe enregistre. Veuillez vous connecter.")

    @staticmethod
    def _parse_transcript(raw: str) -> Optional[TranscriptEvent]:
        """Parse transcript messages coming from the WebSocket."""
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return TranscriptEvent(text=raw, final=False)
        if payload.get("type") != "transcript":
            return None
        text = payload.get("text", "")
        final = bool(payload.get("final", False))
        confidence = payload.get("confidence")
        return TranscriptEvent(text=text, final=final, confidence=confidence)


def detect_server_status(settings: AppSettings) -> Callable[[], bool]:
    """Return a helper that pings the server."""

    async def _ping() -> bool:
        async with httpx.AsyncClient(
            base_url=settings.server.base_url,
            verify=settings.server.verify_ssl,
        ) as client:
            try:
                response = await client.get("/health")
                return response.status_code == 200
            except httpx.HTTPError:
                return False

    return lambda: asyncio.run(_ping())
