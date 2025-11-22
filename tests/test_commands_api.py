from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.api import routes_commands


def test_commands_ack_and_report(tmp_path, monkeypatch) -> None:
    client = TestClient(app)
    ack_path = tmp_path / "commands.log"
    report_path = tmp_path / "commands_learning.log"
    monkeypatch.setattr(routes_commands, "COMMAND_LOG_PATH", ack_path)
    monkeypatch.setattr(routes_commands, "COMMAND_REPORT_PATH", report_path)

    payload = {
        "id": "cmd-open-notepad",
        "display_name": "Ouvrir Notepad",
        "action": "notepad.exe",
        "risk_level": "low",
        "type": "app_launch",
        "status": "accepted",
        "args": ["--demo"],
    }
    resp = client.post("/commands/ack", json=payload)
    assert resp.status_code == 200
    assert ack_path.exists()
    line = ack_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "cmd-open-notepad" in line
    assert "\"status\": \"accepted\"" in line

    report_payload = {
        "command": {
            "id": "cmd-train",
            "display_name": "Script interne",
            "action": "script.bat",
            "risk_level": "medium",
            "type": "script",
        },
        "note": "ajouter au catalogue",
    }
    resp = client.post("/commands/report", json=report_payload)
    assert resp.status_code == 200
    assert report_path.exists()
    reported = report_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "cmd-train" in reported
    assert "ajouter au catalogue" in reported
