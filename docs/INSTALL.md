# Installation

1) Prérequis matériels/OS
- Windows 11, GPU NVIDIA (testé RTX 4070 Ti) avec pilotes à jour + CUDA/cuBLAS.
- Python 3.11, Git.

2) Créer l’environnement Python (uv + venv)
- Installer uv: `pip install uv`
- Cloner le dépôt, puis: `uv pip install -e .[dev]`
- Option Windows: utilisez `scripts\start-server.bat` (crée `.venv`, installe, lance).

3) llama.cpp (CUDA) — llama-cpp-python
- Option rapide (CUDA/cuBLAS): `pip install --upgrade llama-cpp-python[cuda]`
- Ou build local: `set CMAKE_ARGS=-DLLAMA_CUBLAS=1` puis `pip install llama-cpp-python`
- Placez le modèle GGUF (Llama 3.1 8B Instruct Q5_K_M) sous `models/`.
- Définir le chemin modèle:
  - PowerShell: `$env:LLM_MODEL_PATH='models/llama-3.1-8b-instruct.Q5_K_M.gguf'`
  - Bash: `export LLM_MODEL_PATH=models/llama-3.1-8b-instruct.Q5_K_M.gguf`
- `app/core/llm.py` vérifie le fichier et stoppe si introuvable.

4) OCR FR (Tesseract + pdf2image)
- Installer Tesseract (langue `fra`).
- Installer Poppler + pdf2image:
  - Windows: Poppler for Windows (ajouter `bin/` au PATH), `pip install pdf2image`.
  - macOS: `brew install poppler`.
  - Linux: `apt install poppler-utils`.
- Activer/désactiver via `rag_enable_ocr`; langue multi: `rag_ocr_lang=fra+eng`.

5) Embeddings BGE‑M3 (offline)
- `sentence-transformers` est inclus; téléchargez BAAI/bge-m3 au préalable si off‑line (cache HF local).

6) Lancement
- Backend: `uv run python -m app.cli serve` (ou `scripts\start-server.bat`).
- UI dev: `cd webui && npm i && npm run dev` (VITE_API_URL=http://127.0.0.1:8000)
- UI prod: `npm run build` puis `python -m app.cli ui --path webui/dist`

7) Configuration utile (`config.json.example`)
- `allowlist_domains`: ["open-meteo.com", "duckduckgo.com"] (pare‑feu sortant)
- `reset_admin_flag`: `C:\\IVY\\reset_admin.flag`
- RAG: `rag_inbox_dir`, `rag_knowledge_dir`, `rag_index_dir`

Résolution d’erreurs
- Modèle manquant: vérifier `LLM_MODEL_PATH` et le fichier GGUF.
- CUDA non détecté: installer `llama-cpp-python[cuda]` ou recompiler avec `LLAMA_CUBLAS=1`.
- OCR PDF vide: installer Poppler et vérifier `rag_ocr_lang`.
- FAISS non dispo: fallback NumPy (index.npy). Installez `faiss-cpu` pour de meilleures perfs.
