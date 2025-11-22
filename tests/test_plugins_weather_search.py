from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import plugins


@pytest.fixture(autouse=True)
def _reset_registry():
    plugins.REGISTRY.clear()


def test_weather_success_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    plugins.load_plugins()
    assert "weather" in plugins.REGISTRY

    # Stub réseau
    from plugins.weather import plugin as weather_mod

    def fake_get(url: str, timeout: float = 5.0):
        return {
            "current": {"temperature_2m": 12.3, "wind_speed_10m": 4.5},
            "current_units": {"temperature_2m": "°C", "wind_speed_10m": "m/s"},
        }

    monkeypatch.setattr(weather_mod.plugin, "_http_get", lambda url, timeout=5.0: fake_get(url, timeout))
    out = plugins.run("weather", lat=48.85, lon=2.35, lang="fr")
    assert out["temperature"] == 12.3
    assert out["unit_temperature"] == "°C"

    # Timeout
    def fake_timeout(url: str, timeout: float = 5.0):
        raise Exception("timeout")

    monkeypatch.setattr(weather_mod.plugin, "_http_get", lambda url, timeout=5.0: fake_timeout(url, timeout))
    out2 = plugins.run("weather", lat=48.85, lon=2.35, lang="fr")
    assert out2.get("error")


def test_search_success_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    plugins.load_plugins()
    assert "search" in plugins.REGISTRY

    from plugins.search import plugin as search_mod

    def fake_get(url: str, timeout: float = 5.0):
        return {
            "Heading": "Example",
            "AbstractText": "Resultat",
            "AbstractURL": "https://example.com",
        }

    monkeypatch.setattr(search_mod.plugin, "_http_get", lambda url, timeout=5.0: fake_get(url, timeout))
    out = plugins.run("search", query="test")
    assert out["url"] == "https://example.com"

    def fake_timeout(url: str, timeout: float = 5.0):
        raise Exception("timeout")

    monkeypatch.setattr(search_mod.plugin, "_http_get", lambda url, timeout=5.0: fake_timeout(url, timeout))
    out2 = plugins.run("search", query="test")
    assert out2.get("error")

