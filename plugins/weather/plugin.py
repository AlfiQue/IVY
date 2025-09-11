from __future__ import annotations

import time
from typing import Any, Dict
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.firewall import is_url_allowed


class Plugin:
    meta = {
        "name": "weather",
        "permissions": ["net", "fs_read"],
        "description": "Météo via Open-Meteo",
        "inputs": {
            "schema": {
                "lat": (float, ...),
                "lon": (float, ...),
                "lang": (str, "fr"),
            }
        },
    }

    def __init__(self) -> None:
        self._cache: Dict[tuple[float, float, str], tuple[float, Dict[str, Any]]] = {}

    def _allowed(self, url: str) -> bool:
        s = get_settings()
        return is_url_allowed(url, s.allowlist_domains, getattr(s, "allowlist_ports", [80, 443]))

    def _http_get(self, url: str, timeout: float = 5.0) -> Dict[str, Any]:
        if not self._allowed(url):
            raise RuntimeError("Domaine non autorisé par le pare-feu")
        from app.core.firewall import sync_get
        settings = get_settings()
        res = sync_get(
            url,
            allowlist=settings.allowlist_domains,
            ports=getattr(settings, "allowlist_ports", [80, 443]),
            timeout=timeout,
        )
        res.raise_for_status()
        return res.json()

    def run(self, lat: float, lon: float, lang: str = "fr") -> Dict[str, Any]:
        key = (round(lat, 3), round(lon, 3), lang)
        now = time.monotonic()
        # cache 10 minutes
        if key in self._cache and (now - self._cache[key][0]) < 600:
            return {"source": "cache", **self._cache[key][1]}
        try:
            qs = urlencode(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,wind_speed_10m",
                    "timezone": "auto",
                    "lang": lang,
                }
            )
            url = f"https://api.open-meteo.com/v1/forecast?{qs}"
            data = self._http_get(url, timeout=5.0)
            cur = data.get("current") or {}
            out = {
                "temperature": cur.get("temperature_2m"),
                "wind_speed": cur.get("wind_speed_10m"),
                "unit_temperature": data.get("current_units", {}).get("temperature_2m"),
                "unit_wind_speed": data.get("current_units", {}).get("wind_speed_10m"),
            }
            self._cache[key] = (now, out)
            return out
        except httpx.TimeoutException:
            return {"error": "timeout"}
        except Exception as exc:
            return {"error": f"weather_failed: {exc}"}


plugin = Plugin()
