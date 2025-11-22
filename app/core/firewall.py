from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

import httpx


class OutboundBlocked(Exception):
    """Exception levée quand un domaine n'est pas autorisé."""


def is_url_allowed(url: str, allowlist: Iterable[str], ports: Iterable[int] | None = None) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ports_set = set(ports or [80, 443])
    if port not in ports_set:
        return False
    for domain in allowlist:
        if domain.startswith("*"):
            if hostname.endswith(domain[1:]):
                return True
        elif hostname == domain or hostname.endswith("." + domain):
            return True
    return False


def sync_get(url: str, *, allowlist: Iterable[str], ports: Iterable[int] | None = None, **kwargs):
    """Requête GET synchrone filtrée par pare-feu (httpx.Client)."""
    if not is_url_allowed(url, allowlist, ports):
        raise OutboundBlocked(f"Domaine interdit: {url}")
    with httpx.Client() as client:
        return client.get(url, **kwargs)


class FirewallHTTPClient:
    """Client HTTP avec filtrage de domaines autorisés.

    Ce client enveloppe :class:`httpx.AsyncClient` et vérifie que les
    requêtes sortantes ciblent uniquement les domaines figurant dans la liste
    blanche fournie. Il peut être utilisé comme gestionnaire de contexte
    asynchrone afin de garantir la fermeture de la session HTTP.
    """

    def __init__(self, allowlist: Iterable[str], ports: Iterable[int] | None = None) -> None:
        self.allowlist = list(allowlist)
        self.ports = set(ports or [80, 443])
        self.client = httpx.AsyncClient()

    async def __aenter__(self) -> "FirewallHTTPClient":
        return self

    async def __aexit__(
        self, exc_type, exc, tb
    ) -> None:  # pragma: no cover - signature standard
        await self.close()

    async def close(self) -> None:
        """Ferme le client HTTP sous-jacent."""
        await self.client.aclose()

    def _allowed(self, url: str) -> bool:
        return is_url_allowed(url, self.allowlist, self.ports)

    async def get(self, url: str, **kwargs):
        if not self._allowed(url):
            raise OutboundBlocked(f"Domaine interdit: {url}")
        return await self.client.get(url, **kwargs)
