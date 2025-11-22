from __future__ import annotations

import json
import os
import hashlib
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, Iterable, List, Tuple

import numpy as np

import os as _os
faiss = None  # type: ignore
if _os.getenv("IVY_DISABLE_FAISS") != "1":
    try:  # faiss optionnel: fallback numpy si indisponible
        import faiss  # type: ignore
    except Exception:  # pragma: no cover - fallback
        faiss = None  # type: ignore

try:  # embeddings optionnels: fallback hashing si indisponible
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover - fallback
    SentenceTransformer = None  # type: ignore

try:  # OCR optionnel
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - fallback si pillow absent
    pytesseract = None  # type: ignore
    Image = None  # type: ignore

from app.core.config import Settings


TEXT_EXTS = {".txt", ".md", ".rst", ".py", ".json", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
PDF_EXTS = {".pdf"}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize(vecs: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12
    return vecs / n


@dataclass
class RagPaths:
    inbox: Path
    knowledge: Path
    index_dir: Path


class _Embedder:
    def __init__(self) -> None:
        self._model = None
        self.dim = 384  # fallback dimension
        if SentenceTransformer is not None:
            try:  # éviter les téléchargements si offline
                self._model = SentenceTransformer("BAAI/bge-m3")
                # estime la dimension
                emb = self._model.encode(["test"], normalize_embeddings=False)
                self.dim = int(emb.shape[1])
            except Exception:
                self._model = None

    def encode(self, texts: List[str]) -> np.ndarray:
        if self._model is not None:
            arr = self._model.encode(texts, normalize_embeddings=False)
            return np.asarray(arr, dtype=np.float32)
        # Fallback déterministe: hashing -> proj. simple
        rng = np.random.default_rng(0)
        basis = rng.standard_normal((self.dim, 256), dtype=np.float32)
        vecs = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            x = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
            x = (x - 127.5) / 127.5
            x = (basis @ np.resize(x, (256,)))
            vecs.append(x.astype(np.float32))
        return np.vstack(vecs)


class _Index:
    def __init__(self, dim: int, path: Path) -> None:
        self.dim = dim
        self.path = path
        self.faiss_index = None
        self._matrix: np.ndarray | None = None
        self._load()

    def _load(self) -> None:
        idxf = self.path / "index.faiss"
        npf = self.path / "index.npy"
        if faiss is not None and idxf.exists():
            self.faiss_index = faiss.read_index(str(idxf))
        elif npf.exists():
            self._matrix = np.load(npf)
        else:
            self.faiss_index = None
            self._matrix = np.zeros((0, self.dim), dtype=np.float32)

    def add(self, vectors: np.ndarray) -> None:
        if vectors.size == 0:
            return
        if faiss is not None:
            if self.faiss_index is None:
                # index IP + normalisation pour cosinus
                self.faiss_index = faiss.IndexFlatIP(self.dim)
            self.faiss_index.add(_normalize(vectors))
        else:
            if self._matrix is None:
                self._matrix = np.zeros((0, self.dim), dtype=np.float32)
            self._matrix = np.vstack([self._matrix, _normalize(vectors)])

    def search(self, query: np.ndarray, top_k: int) -> Tuple[np.ndarray, np.ndarray]:
        q = _normalize(query).astype(np.float32)
        if faiss is not None and self.faiss_index is not None:
            scores, ids = self.faiss_index.search(q, top_k)
            return scores[0], ids[0]
        mat = self._matrix or np.zeros((0, self.dim), dtype=np.float32)
        if mat.shape[0] == 0:
            return np.array([], dtype=np.float32), np.array([], dtype=np.int64)
        sims = (mat @ q[0])
        top_idx = np.argsort(-sims)[:top_k]
        return sims[top_idx], top_idx

    def save(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if faiss is not None and self.faiss_index is not None:
            faiss.write_index(self.faiss_index, str(self.path / "index.faiss"))
        else:
            np.save(self.path / "index.npy", self._matrix or np.zeros((0, self.dim), dtype=np.float32))


class RAGEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.paths = RagPaths(
            inbox=Path(self.settings.rag_inbox_dir),
            knowledge=Path(self.settings.rag_knowledge_dir),
            index_dir=Path(self.settings.rag_index_dir),
        )
        self.paths.inbox.mkdir(parents=True, exist_ok=True)
        self.paths.knowledge.mkdir(parents=True, exist_ok=True)
        self.paths.index_dir.mkdir(parents=True, exist_ok=True)
        self.embedder = _Embedder()
        self.index = _Index(self.embedder.dim, self.paths.index_dir)
        self.meta_path = self.paths.index_dir / "meta.json"
        self.meta: List[dict[str, Any]] = []
        self._load_meta()

    # ----- Extraction -----
    def _extract_text(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext in TEXT_EXTS:
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return ""
        if ext in PDF_EXTS:
            txt = self._extract_pdf_text(path)
            if txt.strip():
                return txt
            if self.settings.rag_enable_ocr:
                return self._extract_pdf_ocr(path)
            return ""
        if ext in IMAGE_EXTS and self.settings.rag_enable_ocr:
            return self._extract_image_ocr(path)
        return ""

    def _extract_pdf_text(self, path: Path) -> str:
        # Tentatives d'extraction texte PDF si dépendances dispo
        try:
            import PyPDF2  # type: ignore

            text_parts = []
            with path.open("rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts)
        except Exception:
            return ""

    def _extract_pdf_ocr(self, path: Path) -> str:
        if pytesseract is None:
            return ""
        try:
            from pdf2image import convert_from_path  # type: ignore
        except Exception:
            return ""
        try:
            images = convert_from_path(str(path))
            texts: list[str] = []
            for img in images:
                texts.append(self._ocr_image(img))
            return "\n".join(texts)
        except Exception:
            return ""

    def _extract_image_ocr(self, path: Path) -> str:
        if pytesseract is None or Image is None:
            return ""
        try:
            img = Image.open(path)
            return self._ocr_image(img)
        except Exception:
            return ""

    def _parse_ocr_langs(self) -> list[str]:
        raw = (self.settings.rag_ocr_lang or "fra").strip()
        # supporte séparateurs '+', ',' et espaces
        langs = [p for p in re.split(r"[+,\s]+", raw) if p]
        return langs or ["fra"]

    def _ocr_image(self, img) -> str:
        if pytesseract is None:
            return ""
        langs = self._parse_ocr_langs()
        # 1) tenter la combinaison de langues si >1
        if len(langs) > 1:
            try:
                text = pytesseract.image_to_string(img, lang="+".join(langs))
                if text and text.strip():
                    return text
            except Exception:
                pass
        # 2) essayer chaque langue individuellement en repli
        for lg in langs:
            try:
                text = pytesseract.image_to_string(img, lang=lg)
                if text and text.strip():
                    return text
            except Exception:
                continue
        return ""

    # ----- Chunking -----
    def _chunks(self, text: str) -> List[Tuple[int, int, str]]:
        size = int(self.settings.rag_chunk_size)
        overlap = int(self.settings.rag_chunk_overlap)
        if size <= 0:
            return [(0, len(text), text)]
        chunks: List[Tuple[int, int, str]] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            chunk = text[start:end]
            if chunk.strip():
                chunks.append((start, end, chunk))
            if end == len(text):
                break
            start = max(0, end - overlap)
        return chunks

    # ----- Indexation -----
    def _already_indexed(self, sha: str) -> bool:
        return any(m.get("doc_sha256") == sha for m in self.meta)

    def _add_document(self, path: Path, force: bool = False) -> int:
        sha = _sha256_file(path)
        if not force and self._already_indexed(sha):
            return 0
        text = self._extract_text(path)
        if not text.strip():
            return 0
        chunks = self._chunks(text)
        vectors = self.embedder.encode([c[2] for c in chunks])
        self.index.add(vectors)
        added = 0
        stat = path.stat()
        for i, (s, e, ch) in enumerate(chunks):
            self.meta.append(
                {
                    "doc_path": str(path),
                    "doc_sha256": sha,
                    "chunk_id": i,
                    "start": s,
                    "end": e,
                    "text": ch,
                    "size": int(stat.st_size),
                    "mtime": int(stat.st_mtime),
                    "type": path.suffix.lower().lstrip("."),
                }
            )
            added += 1
        return added

    def _iter_files(self) -> Iterable[Path]:
        for base in (self.paths.inbox, self.paths.knowledge):
            if not base.exists():
                continue
            for p in base.rglob("*"):
                if p.is_file():
                    yield p

    def reindex(self, full: bool = True) -> int:
        if full:
            self.meta = []
            self.index = _Index(self.embedder.dim, self.paths.index_dir)
        total = 0
        for path in self._iter_files():
            total += self._add_document(path, force=full)
        self._save()
        return total

    def _load_meta(self) -> None:
        if self.meta_path.exists():
            try:
                self.meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except Exception:
                self.meta = []

    def _save(self) -> None:
        self.index.save()
        self.meta_path.write_text(json.dumps(self.meta, ensure_ascii=False), encoding="utf-8")

    # ----- Requête -----
    def query(self, text: str, top_k: int = 5) -> List[dict[str, Any]]:
        if not self.meta:
            return []
        q = self.embedder.encode([text])
        scores, ids = self.index.search(q, top_k)
        results: List[dict[str, Any]] = []
        for rank, (score, idx) in enumerate(zip(scores.tolist(), ids.tolist())):
            if idx is None or idx < 0 or idx >= len(self.meta):
                continue
            m = self.meta[idx]
            results.append(
                {
                    "rank": rank,
                    "score": float(score),
                    "text": m.get("text", ""),
                    "source": {
                        "path": m.get("doc_path"),
                        "sha256": m.get("doc_sha256"),
                        "chunk_id": m.get("chunk_id"),
                        "start": m.get("start"),
                        "end": m.get("end"),
                    },
                }
            )
        return results

    # ----- Watcher (optionnel, non activé par défaut) -----
    def start_watchers(self) -> None:  # pragma: no cover - délicat en CI
        try:
            from watchdog.observers import Observer  # type: ignore
            from watchdog.events import FileSystemEventHandler  # type: ignore

            class Handler(FileSystemEventHandler):
                def __init__(self, engine: "RAGEngine") -> None:
                    self.engine = engine

                def on_created(self, event):  # type: ignore[override]
                    if not getattr(event, "is_directory", False):
                        self.engine._add_document(Path(event.src_path), force=False)
                        self.engine._save()

                def on_modified(self, event):  # type: ignore[override]
                    if not getattr(event, "is_directory", False):
                        self.engine._add_document(Path(event.src_path), force=True)
                        self.engine._save()

            handler = Handler(self)
            self._observer = Observer()
            for base in (self.paths.inbox, self.paths.knowledge):
                self._observer.schedule(handler, str(base), recursive=True)
            self._observer.start()
        except Exception:
            pass

    def stop_watchers(self) -> None:  # pragma: no cover - délicat en CI
        observer = getattr(self, "_observer", None)
        try:
            if observer is not None:
                observer.stop()
                observer.join(timeout=2)
        except Exception:
            pass

    def start_scheduler(self, interval_minutes: int = 60) -> None:  # pragma: no cover
        try:
            from apscheduler.schedulers.background import (
                BackgroundScheduler,
            )  # type: ignore

            def _job() -> None:
                try:
                    self.reindex(full=False)
                except Exception:
                    pass

            self._scheduler = BackgroundScheduler(daemon=True)
            self._scheduler.add_job(_job, "interval", minutes=int(interval_minutes))
            self._scheduler.start()
        except Exception:
            pass

    def stop_scheduler(self) -> None:  # pragma: no cover
        sched = getattr(self, "_scheduler", None)
        try:
            if sched is not None:
                sched.shutdown(wait=False)
        except Exception:
            pass
