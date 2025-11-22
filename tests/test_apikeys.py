from __future__ import annotations

from app.core import apikeys


def test_apikeys_create_and_verify(tmp_path, monkeypatch):
    # redirect storage to temp file
    monkeypatch.setattr(apikeys, "_FILE", tmp_path / "apikeys.json", raising=False)
    created = apikeys.create_key("test", ["llm"])  # returns clear key once
    assert created["id"] and created["key"] and created["name"] == "test"
    # Listing masks hash
    listed = apikeys.list_keys()
    assert len(listed) == 1
    # Verify
    ok = apikeys.verify_token(created["key"], ["llm"])  # correct scope
    assert ok and ok.get("sub", "").startswith("api:")
    bad = apikeys.verify_token("badtoken", ["llm"])  # wrong token
    assert bad is None
    # scope mismatch
    mismatch = apikeys.verify_token(created["key"], ["rag"])  # missing scope
    assert mismatch is None
    # delete
    assert apikeys.delete_key(created["id"]) is True
    assert apikeys.delete_key(created["id"]) is False

