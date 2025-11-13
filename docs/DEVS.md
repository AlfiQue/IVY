# Guide developpeurs

## Outils
- Python 3.11, Git.
- Installation projet : `py -m pip install -e .[dev]`
- Node.js 18+ pour le dossier `webui/`.

## Arborescence principale
- `app/api/` : routes FastAPI (`chat`, `memory`, `debug`, `jeedom`, `history`, `jobs`, ...).
- `app/core/` : logique metier (chat_store, chat_engine, embeddings, websearch DuckDuckGo, LLMClient, jobs, etc.).
- `webui/` : UI Vite/React/TypeScript (pages Chat, Memoire, Debug, Jeedom...).
- `desktop/` : app Tauri Windows (STT/TTS) – optionnel.
- `docs/` : documentation (guides utilisateur, quickstart, API).

## Backend
- Lancement : `python -m app.cli serve` (config via `config.json` ou `.env`).
- Test rapide :
  ```bash
  py -m pytest tests/test_chat_api.py tests/test_history_api.py tests/test_health.py -q
  ```
- Modules clefs :
  - `chat_store` (SQLite) et `chat_engine` (similarite, classification LLM/heuristique, web search, generation).
  - `websearch` (DuckDuckGo via `duckduckgo-search` 5.3.0), `embeddings` (SentenceTransformers), client LLM (llama.cpp ou TensorRT-LLM).
  - `llm.py` : client unifie (llama.cpp par defaut, TensorRT-LLM en option).

## Frontend
- Installation :
  ```bash
  cd webui
  npm install
  npm run dev   # Vite 5173
  ```
- Build : `npm run build` puis `python -m app.cli ui --path webui/dist`.
- Lint/format : `npm run lint`, `npm run format`.

## Qualite
- Python : ruff, black, isort (via `pyproject.toml` et `pre-commit` si besoin).
- Audits optionnels : `pip-audit`, `bandit`.
- Front : ESLint/Prettier (scripts npm).

## Tests
- API memoire/chat/health (cf. commande ci-dessus).
- Tests historiques (RAG, auth, backups…) a adapter selon besoins – plusieurs suites ont ete deposees avec l’ancien systeme de plugins.

## Points d’attention
- Plus de repertoire `plugins/` ni de CLI plugin : toute extension passe par les routes/clients internes.
- `config.json.example` documente les parametres (chat, embeddings, DuckDuckGo, Ollama, Jeedom…).
- Pensez a initialiser la base : `python -m app.cli serve` cree le schema puis `python - <<'PY' ...` pour purger via `chat_store.clear_all()`.

Bon dev !
