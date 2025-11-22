from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np

from app.core.config import Settings
from app.core import rag as rag_module


class DummyEmbedder:
    def __init__(self) -> None:
        self.dim = 8

    def encode(self, texts: List[str]) -> np.ndarray:
        arr = []
        for t in texts:
            v = np.zeros(self.dim, dtype=np.float32)
            v[0] = float(len(t))
            v[1] = float(sum(ord(c) for c in t) % 97)
            v[2] = float(t.count("e"))
            arr.append(v)
        return np.vstack(arr)


def _engine(tmp_path: Path, monkeypatch) -> rag_module.RAGEngine:
    s = Settings(
        rag_inbox_dir=str(tmp_path / "inbox"),
        rag_knowledge_dir=str(tmp_path / "knowledge"),
        rag_index_dir=str(tmp_path / "index"),
        rag_chunk_size=50,
        rag_chunk_overlap=10,
        rag_enable_ocr=True,
    )
    monkeypatch.setattr(rag_module, "_Embedder", lambda: DummyEmbedder())
    return rag_module.RAGEngine(s)


def test_reindex_and_query(tmp_path: Path, monkeypatch) -> None:
    eng = _engine(tmp_path, monkeypatch)
    txt = eng.paths.knowledge / "note.txt"
    eng.paths.knowledge.mkdir(parents=True, exist_ok=True)
    txt.write_text("Bonjour Paris. La météo est clémente aujourd'hui.")

    count = eng.reindex(full=True)
    assert count > 0
    assert (eng.paths.index_dir / "index.npy").exists() or (eng.paths.index_dir / "index.faiss").exists()
    assert (eng.paths.index_dir / "meta.json").exists()

    res = eng.query("météo Paris", top_k=3)
    assert isinstance(res, list)
    assert res and "source" in res[0] and "text" in res[0]


def test_pdf_scanned_vs_text(tmp_path: Path, monkeypatch) -> None:
    eng = _engine(tmp_path, monkeypatch)
    # simuler PDF
    pdf = eng.paths.inbox / "doc.pdf"
    eng.paths.inbox.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4 mock")

    # forcer extraction texte PDF vide et OCR renvoyant un contenu
    monkeypatch.setattr(eng, "_extract_pdf_text", lambda p: "")
    monkeypatch.setattr(eng, "_extract_pdf_ocr", lambda p: "Texte OCR scanne")

    count = eng.reindex(full=True)
    assert count > 0
    res = eng.query("OCR", top_k=1)
    assert res and "Texte" in res[0]["text"]


def test_watcher_like_addition(tmp_path: Path, monkeypatch) -> None:
    eng = _engine(tmp_path, monkeypatch)
    f1 = eng.paths.inbox / "a.txt"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("alpha beta gamma")
    assert eng.reindex(full=True) > 0

    f2 = eng.paths.inbox / "b.txt"
    f2.write_text("delta epsilon zeta")
    added = eng._add_document(f2, force=False)
    eng._save()
    assert added > 0
    res = eng.query("epsilon", top_k=2)
    assert res and any("epsilon" in r["text"] for r in res)

