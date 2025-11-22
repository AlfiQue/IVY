# Guide Développeurs

Outillage & workflow
- Python 3.11, uv (`pip install uv`).
- Installer: `uv pip install -e .[dev]`
- Lancer: `uv run python -m app.cli serve` (backend), `cd webui && npm i && npm run dev` (front).

Structure du dépôt (principaux)
- `app/`: FastAPI + API (`app/api/*`), core (`app/core/*`), CLI (`app/cli.py`).
- `plugins/`: plugins (dont `_template/`).
- `tests/`: pytest (unit/intégration).
- `webui/`: UI Vite/React/TS.
- `desktop/`: App Tauri Windows (STT/TTS).

Tests & couverture
- `pytest -q` (voir `pytest.ini`): cov ≥ 85% (`--cov-fail-under=85`).
- E2E (Playwright): `cd webui && npm run test:e2e` (backend/front en marche).

Qualité
- pre‑commit: `pre-commit install` puis hooks (ruff, black, isort, trailing, eof). `pip-audit` et `bandit` disponibles (stages: manual).

Lint & format (front-end)
- Web UI (Vite/React/TS):
  - `cd webui && npm i`
  - Lint: `npm run lint` ; Auto-fix: `npm run lint:fix` ; Format: `npm run format`
- Desktop (Tauri/TS):
  - `cd desktop && npm i`
  - Lint: `npm run lint` ; Auto-fix: `npm run lint:fix` ; Format: `npm run format`
- Intégration (option): exécuter ces commandes avant commit/PR ou les brancher dans votre pipeline CI.

Conventions de commits
- Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, etc. Utilisé pour le changelog.

Ajouter un plugin
- `python -m app.cli plugin scaffold monplugin` puis compléter le `meta` et la méthode `run`.
- Respecter les `permissions` et l’allowlist réseau.

Publier une version
- Tag Git (ex: `v0.1.0`), mettre à jour `pyproject.toml` si nécessaire, générer les builds front/desktop au besoin.
