# OCR PDF et Images

Ce projet supporte l’OCR pour les PDF scannés et les images afin d’alimenter l’index RAG.

Prérequis
- Tesseract (binaire) avec le langage français installé (`fra`).
- Python: `pytesseract` (déjà dépendance du projet).
- Optionnel (recommandé pour PDF scannés): `pdf2image` + Poppler.

Installation Poppler
- Linux: installez `poppler-utils` et assurez-vous que `pdftoppm` est dans le `PATH`.
- macOS: `brew install poppler`.
- Windows: installez “Poppler for Windows” et ajoutez le dossier `bin/` au `PATH`.

Activation
- Lorsque `pdf2image` est installé, l’extraction OCR des PDF est automatiquement activée.
- Sinon, l’indexeur tente d’abord l’extraction du texte natif PDF; si indisponible, l’OCR PDF est ignoré.

Paramètres (config.json ou .env)
- `rag_enable_ocr=true`
- `rag_inbox_dir=app/data/inbox`
- `rag_knowledge_dir=app/data/knowledge`
- `rag_index_dir=app/data/faiss_index`
- `rag_chunk_size=1000`
- `rag_chunk_overlap=200`
- `rag_reindex_interval_minutes=60`

Notes
- L’OCR utilise la langue `fra` par défaut.
- L’index FAISS est persistant sous `app/data/faiss_index`; un fallback NumPy est utilisé si FAISS n’est pas disponible.
