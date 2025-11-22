from app.core.websearch import refine_search_query, _should_ignore_query


def test_refine_search_query_removes_stop_words():
    query = "Quel est le PIB de la France ?"
    refined = refine_search_query(query)
    assert "pib" in refined
    assert "france" in refined
    assert "quel" not in refined


def test_refine_search_query_keeps_semantic_tokens_when_short():
    query = "AI"
    refined = refine_search_query(query)
    assert refined.lower() == "ai"


def test_should_ignore_question_word_only_queries():
    ignore, reason = _should_ignore_query("Quoi ?")
    assert ignore is True
    assert reason in {"question_word_only", "placeholder_short", "no_semantic_token"}


def test_should_not_ignore_structured_queries():
    ignore, reason = _should_ignore_query("Quel est le prix de l'électricité ?")
    assert ignore is False
    assert reason is None
