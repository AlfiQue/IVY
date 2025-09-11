# IVY — Assistant local (Docs)

Vision
- IVY est un assistant local, privé et extensible: LLM on‑prem (llama.cpp CUDA), RAG local (OCR + FAISS), plugins Python à chaud, API HTTP/WebSocket, UI Web (PWA) et Desktop (Tauri Windows).

Fonctionnalités clés
- LLM local (Llama 3.1 8B Q5_K_M) avec streaming WS et function‑calling vers plugins.
- RAG local: OCR FR (Tesseract, pdf2image), embeddings BGE‑M3, FAISS persistant, watcher FS.
- Sécurité: JWT + CSRF, rate‑limit, pare‑feu sortant (allowlist domaines), audit.
- Plugins à chaud (upload ZIP, hot‑reload, crash‑dump), tâches planifiées (APScheduler), sauvegardes ZIP.
- UI Web FR (PWA mobile) + App Desktop Windows (STT Whisper.cpp, TTS Coqui).

Flux général
1) Démarrer le serveur → UI (webui) → login admin → config/allowlist → activer plugins.
2) Charger/Indexer des documents (RAG) → Requêtes LLM/RAG → Observabilité via /health et logs JSONL.
3) Planifier des tâches (plugins/backup), gérer sessions, exporter/importer sauvegardes.

Captures d’écran (placeholders)
- Ajoutez des images dans `docs/img/` puis référencez‑les: `![Plugins](img/plugins.png)`.

Liens internes
- Installation: INSTALL.md
- Guide utilisateur: USER_GUIDE.md
- Plugins: PLUGINS.md
- API: API.md
- Sécurité: SECURITY.md
- Sauvegardes: BACKUP_RESTORE.md
- Guide dev: DEVS.md

Qualité & CI (résumé)
- Python: pre-commit (ruff/black/isort), tests (pytest ≥85% via pytest.ini), sécurité (pip-audit, bandit).
- Frontend: ESLint/Prettier (webui et desktop).
  - Web UI: `cd webui && npm i && npm run lint` ; Desktop: `cd desktop && npm i && npm run lint`.
  - Auto-fix/format: `npm run lint:fix` et `npm run format` dans chaque dossier.
