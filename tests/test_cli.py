from __future__ import annotations

from typer.testing import CliRunner

from app import cli as cli_module


runner = CliRunner()


def test_cli_help():
    result = runner.invoke(cli_module.cli, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output and "task" in result.output


def test_cli_task_commands_parse():
    res_get = runner.invoke(cli_module.cli, ["task", "get", "nonexistent"])
    assert res_get.exit_code == 0
    res_cancel = runner.invoke(cli_module.cli, ["task", "cancel", "nonexistent"])
    assert res_cancel.exit_code == 0
    res_update = runner.invoke(cli_module.cli, ["task", "update", "nonexistent", "--params", "{}", "--schedule", "{}"])
    assert res_update.exit_code == 0
