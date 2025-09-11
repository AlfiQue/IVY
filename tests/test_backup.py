from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core import config as config_module
from app.main import app


@pytest.mark.asyncio
async def test_export_then_import_dryrun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Préparer des fichiers
    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    db = tmp_path / "history.db"
    db.write_bytes(b"\x00\x01")
    idx = tmp_path / "faiss"
    idx.mkdir()
    (idx / "index.npy").write_bytes(b"\x00")
    (idx / "meta.json").write_text("[]")

    s = Settings(db_path=str(db), rag_index_dir=str(idx))
    monkeypatch.setattr(config_module, "get_settings", lambda: s, raising=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # login to get CSRF token for import
        login = await ac.post("/auth/login", json={"user": "admin", "password": "admin"})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        # export
        resp = await ac.get("/backup/export")
        assert resp.status_code == 200
        content = resp.content
        with zipfile.ZipFile(BytesIO(content)) as zf:
            names = zf.namelist()
            assert any(n.startswith("faiss_index/") for n in names) or "index.npy" in names
        # import (dry-run)
        files = {"file": ("backup.zip", content, "application/zip")}
        resp2 = await ac.post("/backup/import?dry_run=true", files=files, headers={"X-CSRF-Token": csrf})
        assert resp2.status_code == 200
        plan = resp2.json()["plan"]
        assert isinstance(plan, list)
