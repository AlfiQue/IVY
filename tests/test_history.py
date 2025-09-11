import pytest

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
