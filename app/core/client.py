from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

import httpx

class IvyClient:
    """Client Python minimal pour l'API IVY (REST + WS streaming).

    - Utilisation admin (UI): login pour obtenir les cookies (peu utile cote script).
    - Utilisation apps: fournir `api_key` pour Authorization: Bearer.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: Optional[str] = None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout)
        self._async = httpx.AsyncClient(timeout=timeout)
        self._csrf: Optional[str] = None

    # ----- helpers -----
    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    # ----- Auth (admin) -----
    def login_admin(self, user: str, password: str) -> Dict[str, Any]:
        r = self._client.post(f"{self.base_url}/auth/login", json={"user": user, "password": password})
        r.raise_for_status()
        data = r.json()
        self._csrf = data.get("csrf_token")
        return data

    def _headers_csrf(self) -> Dict[str, str]:
        h = self._headers()
        if self._csrf:
            h["X-CSRF-Token"] = self._csrf
        return h

    # ----- API Keys (admin) -----
    def list_keys(self) -> Dict[str, Any]:
        r = self._client.get(f"{self.base_url}/apikeys", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def create_key(self, name: str, scopes: Optional[list[str]] = None) -> Dict[str, Any]:
        r = self._client.post(f"{self.base_url}/apikeys", headers=self._headers(), json={"name": name, "scopes": scopes or []})
        r.raise_for_status()
        return r.json()

    def delete_key(self, key_id: str) -> Dict[str, Any]:
        r = self._client.delete(f"{self.base_url}/apikeys/{key_id}", headers=self._headers())
        r.raise_for_status()
        return r.json()

    # ----- Config (admin) -----
    def get_config(self) -> Dict[str, Any]:
        r = self._client.get(f"{self.base_url}/config", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def update_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        r = self._client.put(f"{self.base_url}/config", headers=self._headers(), json=patch)
        r.raise_for_status()
        return r.json()

    # ----- LLM -----
    def infer(self, prompt: str, conversation_id: Optional[int] = None) -> str:
        payload: Dict[str, Any] = {"question": prompt}
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        r = self._client.post(f"{self.base_url}/chat/query", headers=self._headers(), json=payload)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            answer = data.get("answer")
            if answer:
                return str(answer)
            answer_message = data.get("answer_message")
            if isinstance(answer_message, dict):
                content = answer_message.get("content")
                if content:
                    return str(content)
        return ""

    # ----- Misc -----
    def health(self) -> Dict[str, Any]:
        r = self._client.get(f"{self.base_url}/health")
        r.raise_for_status()
        return r.json()

    # ----- RAG -----
    def rag_reindex(self, full: bool = True) -> Dict[str, Any]:
        r = self._client.post(f"{self.base_url}/rag/reindex", headers=self._headers(), json={"full": full})
        r.raise_for_status()
        return r.json()

    def rag_query(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        r = self._client.post(f"{self.base_url}/rag/query", headers=self._headers(), json={"query": query, "top_k": top_k})
        r.raise_for_status()
        return r.json()

    # ----- Jobs -----
    def list_jobs(self) -> Dict[str, Any]:
        r = self._client.get(f"{self.base_url}/jobs", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def get_job(self, job_id: str) -> Dict[str, Any]:
        r = self._client.get(f"{self.base_url}/jobs/{job_id}", headers=self._headers())
        r.raise_for_status()
        return r.json()

    # Admin-only job mutations (JWT cookie + CSRF)
    def add_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self._client.post(f"{self.base_url}/jobs/add", headers=self._headers_csrf(), json=payload)
        r.raise_for_status()
        return r.json()

    def run_job_now(self, job_id: str) -> Dict[str, Any]:
        r = self._client.post(f"{self.base_url}/jobs/{job_id}/run-now", headers=self._headers_csrf())
        r.raise_for_status()
        return r.json()

    def delete_job(self, job_id: str) -> Dict[str, Any]:
        r = self._client.delete(f"{self.base_url}/jobs/{job_id}", headers=self._headers_csrf())
        r.raise_for_status()
        return r.json()

    # ----- History -----
    def list_history(self, **params: Any) -> Dict[str, Any]:
        r = self._client.get(f"{self.base_url}/history", headers=self._headers(), params=params)
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
        try:
            asyncio.get_event_loop().run_until_complete(self._async.aclose())
        except Exception:
            pass

    # ----- Backup (admin) -----
    def export_backup(self, include_logs: bool = False, to_path: Optional[str] = None):
        """Exporte une sauvegarde. Si `to_path` est fourni, écrit le fichier et retourne le chemin, sinon retourne les octets."""
        params = {"include_logs": str(include_logs).lower()}
        # Admin-only => utiliser cookies (login_admin avant)
        r = self._client.get(f"{self.base_url}/backup/export", params=params, headers=self._headers())
        r.raise_for_status()
        data = r.content
        if to_path:
            with open(to_path, "wb") as f:
                f.write(data)
            return to_path
        return data

    def import_backup(self, zip_path: str, dry_run: bool = True) -> Dict[str, Any]:
        # Admin-only + CSRF
        data = Path(zip_path).read_bytes()
        files = {"file": (Path(zip_path).name, data, "application/zip")}
        headers = self._headers_csrf()
        r = self._client.post(f"{self.base_url}/backup/import", params={"dry_run": str(dry_run).lower()}, headers=headers, files=files)
        r.raise_for_status()
        return r.json()

    # ----- Sessions (admin) -----
    def list_sessions_admin(self) -> Dict[str, Any]:
        r = self._client.get(f"{self.base_url}/sessions", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def terminate_session_admin(self, session_id: str) -> Dict[str, Any]:
        r = self._client.post(f"{self.base_url}/sessions/{session_id}/terminate", headers=self._headers_csrf())
        r.raise_for_status()
        return r.json()

