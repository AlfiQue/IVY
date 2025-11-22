from __future__ import annotations

from pathlib import Path
import io
import zipfile

import pytest

from app.core import plugins

PLUGIN_TEMPLATE = """
from pathlib import Path
COUNTER = Path(__file__).with_name("counter.txt")
STATE = Path(__file__).with_name("state.txt")

class Plugin:
    def __init__(self):
        self.meta = {"name": "dummy"}

    def start(self):
        value = 0
        if COUNTER.exists():
            value = int(COUNTER.read_text())
        COUNTER.write_text(str(value + 1))
        STATE.write_text("running")

    def stop(self):
        STATE.write_text("stopped")

    def run(self, x: int) -> int:
        return x * 2

plugin = Plugin()
"""


@pytest.fixture(autouse=True)
def _cleanup():
    plugins.REGISTRY.clear()


def test_plugin_lifecycle(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "dummy"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(PLUGIN_TEMPLATE)

    plugins.load_plugins(tmp_path)
    plugins.enable("dummy")
    plugins.start("dummy")
    assert (plugin_dir / "counter.txt").read_text() == "1"
    assert plugins.run("dummy", x=2) == 4

    (plugin_dir / "plugin.py").write_text(PLUGIN_TEMPLATE)
    plugins.reload("dummy")
    assert (plugin_dir / "counter.txt").read_text() == "2"

    plugins.stop("dummy")
    assert (plugin_dir / "state.txt").read_text() == "stopped"

    plugins.delete("dummy")
    assert "dummy" not in plugins.REGISTRY
    assert not plugin_dir.exists()


def test_disable_stops_plugin(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "dummy"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(PLUGIN_TEMPLATE)

    plugins.load_plugins(tmp_path)
    plugins.enable("dummy")
    plugins.start("dummy")
    assert (plugin_dir / "counter.txt").read_text() == "1"
    assert (plugin_dir / "state.txt").read_text() == "running"

    plugins.disable("dummy")
    assert (plugin_dir / "state.txt").read_text() == "stopped"
    assert plugins.REGISTRY["dummy"]["state"] == "disabled"


def test_crash_creates_dump(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_dir = tmp_path / "boom"
    plugin_dir.mkdir()
    plugin_dir.joinpath("plugin.py").write_text(
        """
class Plugin:
    meta = {"name": "boom"}
    def start(self):
        raise RuntimeError('boom')
    def run(self, **kwargs):
        return None
plugin = Plugin()
"""
    )
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(plugins, "LOG_DIR", log_dir)

    plugins.load_plugins(tmp_path)
    plugins.enable("boom")
    with pytest.raises(RuntimeError):
        plugins.start("boom")
    assert any((log_dir).glob("boom-*.log"))


def test_reload_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_dir = tmp_path / "dummy"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(PLUGIN_TEMPLATE)
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(plugins, "LOG_DIR", log_dir)

    plugins.load_plugins(tmp_path)
    plugins.enable("dummy")
    plugins.start("dummy")
    assert plugins.run("dummy", x=3) == 6

    plugin_dir.joinpath("plugin.py").write_text(
        """
class Plugin:
    meta = {"name": "dummy"}
    def start(self):
        raise RuntimeError('boom')
    def run(self, **kwargs):
        return None
plugin = Plugin()
"""
    )

    with pytest.raises(RuntimeError):
        plugins.reload("dummy")

    assert plugins.run("dummy", x=2) == 4
    assert any((log_dir).glob("dummy-*.log"))


def test_upload_zip_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Construire une archive ZIP en mémoire
    content = (
        "class Plugin:\n"
        "    meta = {\"name\": \"zipper\"}\n"
        "    def run(self, x: int) -> int:\n"
        "        return x + 1\n"
        "plugin = Plugin()\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("zipper/plugin.py", content)
    data = buf.getvalue()

    # Rediriger le dossier des plugins vers tmp
    monkeypatch.setattr(plugins, "PLUGIN_DIR", tmp_path)
    name = plugins.install_zip(data)
    assert name == "zipper"
    assert (tmp_path / "zipper" / "plugin.py").exists()

    plugins.load_plugins(tmp_path)
    plugins.enable("zipper")
    assert plugins.run("zipper", x=1) == 2


def test_unknown_permissions_error(tmp_path: Path) -> None:
    p = tmp_path / "bad"
    p.mkdir()
    p.joinpath("plugin.py").write_text(
        """
class Plugin:
    meta = {"name": "bad", "permissions": ["unknown"]}
    def run(self, **kwargs):
        return None
plugin = Plugin()
"""
    )
    with pytest.raises(plugins.PluginError):
        plugins.load_plugins(tmp_path)
