from __future__ import annotations

from app.core import plugins


def test_system_info_fields() -> None:
    plugins.load_plugins()
    out = plugins.run("system_info")
    assert isinstance(out, dict)
    assert "os" in out and "cpu" in out and "gpu" in out and "ram" in out

