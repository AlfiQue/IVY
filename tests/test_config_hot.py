from __future__ import annotations

from app.core.config import get_settings
from pathlib import Path
import json


def test_config_hot_reload(tmp_path, monkeypatch):
    # use temp config.json
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"rate_limit_rps": 5}), encoding="utf-8")
    # Patch config path resolver
    from app.core import config as config_module

    def _custom_source() -> dict[str, object]:
        try:
            return json.loads(cfg.read_text())
        except Exception:
            return {}

    monkeypatch.setattr(config_module.Settings, "json_config_settings_source", staticmethod(_custom_source))
    get_settings.cache_clear()  # type: ignore[attr-defined]
    s = get_settings()
    assert s.rate_limit_rps == 5
    # Update file
    cfg.write_text(json.dumps({"rate_limit_rps": 7}), encoding="utf-8")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    s2 = get_settings()
    assert s2.rate_limit_rps == 7

