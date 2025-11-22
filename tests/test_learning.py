import asyncio

import pytest

from app.core import learning
from app.core.config import get_settings


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "learning.db"))
    get_settings.cache_clear()
    learning._TABLE_READY = False  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()
    learning._TABLE_READY = False  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_learning_events_and_insights(temp_db):
    await learning.record_event(
        question="Quelles sont les activités IA aujourd'hui ?",
        normalized_query="activites ia aujourd",
        classification={"needs_search": True},
        needs_search=True,
        search_query="activites ia",
        search_results_count=2,
        latency_ms=1200.0,
        origin="internet",
    )
    await learning.record_event(
        question="Quelles sont les activités IA aujourd'hui ?",
        normalized_query="activites ia aujourd",
        classification={"needs_search": True},
        needs_search=True,
        search_query="activites ia",
        search_results_count=0,
        latency_ms=1500.0,
        origin="internet",
    )
    await learning.record_event(
        question="Combien de licences disponibles ?",
        normalized_query="licences disponibles",
        classification={"needs_search": False},
        needs_search=False,
        search_query="",
        search_results_count=0,
        latency_ms=800.0,
        origin="llm",
    )

    top = await learning.top_queries()
    assert top, "top queries should not be empty"
    assert top[0]["query"] == "activites ia aujourd"
    assert top[0]["occurrences"] == 2

    unresolved = await learning.unresolved_queries()
    assert unresolved[0]["query"] == "activites ia aujourd"

    recent = await learning.recent_events()
    assert len(recent) == 3
    assert recent[0]["question"]
    assert isinstance(recent[0]["classification"], dict)

    summary = await learning.build_learning_summary(limit_prompts=2, limit_jobs=2, query_limit=2)
    assert "job_recommendations" in summary
    assert summary["job_recommendations"][0]["query"] == "activites ia aujourd"
