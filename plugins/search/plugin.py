from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.firewall import is_url_allowed


class Plugin:
    meta = {
        "name": "search",
        "permissions": ["net", "fs_read"],
        "description": "Recherche (DuckDuckGo) – 1er résultat",
        "inputs": {"schema": {"query": (str, ...)}},
    }

    def _allowed(self, url: str) -> bool:
        s = get_settings()
        return is_url_allowed(url, s.allowlist_domains, getattr(s, "allowlist_ports", [80, 443]))

    def _http_get(self, url: str, timeout: float = 5.0) -> Dict[str, Any]:
        if not self._allowed(url):
            raise RuntimeError("Domaine non autorisé par le pare-feu")
        from app.core.firewall import sync_get
        s = get_settings()
        res = sync_get(
            url,
            allowlist=s.allowlist_domains,
            ports=getattr(s, "allowlist_ports", [80, 443]),
            timeout=timeout,
        )
        res.raise_for_status()
        return res.json()

    def run(self, query: str) -> Dict[str, Any]:
        try:
            qs = urlencode({"q": query, "format": "json", "no_html": 1})
            url = f"https://api.duckduckgo.com/?{qs}"
            data = self._http_get(url, timeout=5.0)
            # Essayer Abstract
            if data.get("AbstractText") and data.get("AbstractURL"):
                return {
                    "title": data.get("Heading") or "",
                    "snippet": data.get("AbstractText"),
                    "url": data.get("AbstractURL"),
                }
            # Sinon RelatedTopics
            topics = data.get("RelatedTopics") or []
            for t in topics:
                if "Text" in t and "FirstURL" in t:
                    return {"title": "", "snippet": t["Text"], "url": t["FirstURL"]}
            return {"error": "no_results"}
        except httpx.TimeoutException:
            return {"error": "timeout"}
        except Exception as exc:
            return {"error": f"search_failed: {exc}"}


plugin = Plugin()
