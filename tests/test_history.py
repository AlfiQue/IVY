import pytest

from app.core import history
from app.core.history import insert_event, list_events, ping_db


@pytest.mark.asyncio
async def test_insert_and_list_events(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "history.db"))
    assert await ping_db() is True
    await insert_event("test", {"a": 1})
    await insert_event("test2", "payload")
    events = await list_events(10)
    assert len(events) == 2
    assert events[0]["type"] == "test2"
    assert events[1]["payload"] == {"a": 1}


def test_log_event_sync_runs_insert(monkeypatch) -> None:
    recorded: list[tuple[str, dict[str, object]]] = []

    async def fake_insert(event_type: str, payload):
        recorded.append((event_type, payload))

    monkeypatch.setattr(history, "insert_event", fake_insert)
    history.log_event_sync("audit", {"foo": "bar"})
    assert recorded == [("audit", {"foo": "bar"})]
