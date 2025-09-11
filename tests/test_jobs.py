from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.core import plugins
from app.core.jobs import jobs_manager as jm
from app.core import jobs as jobs_module


@pytest.fixture(autouse=True)
def _start_scheduler():
    jm.start()
    yield
    jm.shutdown()


def test_tasks_plugin_crud_and_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Prépare un plugin 'ok' qui écrit un fichier lors du run
    base = tmp_path / "ok"
    base.mkdir(parents=True)
    target = tmp_path / "out.txt"
    base.joinpath("plugin.py").write_text(
        f"""
class Plugin:
    meta = {{"name": "ok"}}
    def start(self):
        pass
    def run(self, **kwargs):
        Path({repr(str(target))}).write_text("done")
plugin = Plugin()
"""
    )
    monkeypatch.setattr(plugins, "PLUGIN_DIR", tmp_path)

    # Charger le plugin 'tasks' du repo et créer un job plugin 'ok'
    plugins.load_plugins()  # charge 'tasks' depuis le dépôt
    assert "tasks" in plugins.REGISTRY

    spec = {"type": "plugin", "params": {"name": "ok", "params": {}}, "schedule": {"trigger": "date"}}
    res = plugins.run("tasks", action="create", spec=spec)
    jid = res["id"]
    assert jid

    # run-now et attendre l'effet
    plugins.run("tasks", action="run_now", spec={"id": jid})
    for _ in range(50):
        if target.exists():
            break
        time.sleep(0.05)
    assert target.exists()

    # list
    jobs = plugins.run("tasks", action="list")
    assert any(j["id"] == jid for j in jobs["jobs"])  # type: ignore[index]

    # delete
    out = plugins.run("tasks", action="delete", spec={"id": jid})
    assert out["deleted"] is True


def test_retry_on_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Accélère les retries
    monkeypatch.setattr(jobs_module, "RETRY_DELAYS", [0, 0, 0])

    # Plugin qui lève systématiquement
    base = tmp_path / "boom"
    base.mkdir(parents=True)
    base.joinpath("plugin.py").write_text(
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
    monkeypatch.setattr(plugins, "PLUGIN_DIR", tmp_path)

    # Création via tasks
    plugins.load_plugins()
    spec = {"type": "plugin", "params": {"name": "boom", "params": {}}, "schedule": {"trigger": "date"}}
    jid = plugins.run("tasks", action="create", spec=spec)["id"]
    plugins.run("tasks", action="run_now", spec={"id": jid})

    # Attendre que les retries s'épuisent
    for _ in range(100):
        items = jm.list_jobs()
        cur = next((x for x in items if x["id"] == jid), None)
        if cur and cur["status"] in {"FAILED", "SUCCESS"}:
            break
        time.sleep(0.05)
    cur = next((x for x in jm.list_jobs() if x["id"] == jid), None)
    assert cur is not None and cur["status"] == "FAILED"

