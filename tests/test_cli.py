from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from app import cli as cli_module


runner = CliRunner()


def test_cli_help():
    result = runner.invoke(cli_module.cli, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output and "plugin" in result.output


def test_cli_scaffold_plugin(tmp_path: Path, monkeypatch):
    out_dir = tmp_path / "plugins"
    result = runner.invoke(cli_module.cli, ["plugin", "scaffold", "demo", "--dir", str(out_dir)])
    assert result.exit_code == 0
    assert (out_dir / "demo" / "plugin.py").exists()


def test_cli_task_get_and_cancel_parsing():
    res_get = runner.invoke(cli_module.cli, ["task", "get", "nonexistent"])
    assert res_get.exit_code == 0
    res_cancel = runner.invoke(cli_module.cli, ["task", "cancel", "nonexistent"])
    assert res_cancel.exit_code == 0
    res_update = runner.invoke(cli_module.cli, ["task", "update", "nonexistent", "--params", "{}", "--schedule", "{}"])
    assert res_update.exit_code == 0
