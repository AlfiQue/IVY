# IVY

Assistant local combinant API FastAPI, orchestrateur de tâches et consoles vocales/web.

## Démarrage rapide

1. Clonez le dépôt puis exécutez `scripts/start-menu.bat`.
2. L’option `[2]` installe l’environnement Python (editable + dépendances).
3. L’option `[3]` lance l’API (`uvicorn app.main:app`) sur `http://127.0.0.1:8000`.
4. L’option `[4]` démarre l’UI Vite (5173) et `[6]` sert l’UI buildée (5174).
5. L’option `[17]` ouvre la page « Tâches & Programmation » (`/task-hub`) et `[18]` packagera la console vocale (PyInstaller) dans `dist/voice_client/IVYVoice`.

## Fonctionnalités majeures

- **Task Hub & Planification** : tableau de bord regroupant l’état des jobs (LLM, RAG, backup, plugins), leurs prochaines exécutions et les actions rapides (run/cancel). Les suggestions auto-learning y affichent prompts récents/favoris, jobs fiables et actions à automatiser.
- **Auto-apprentissage progressif** : le module `app/core/learning.py` stocke les recherches, besoins RAG et conversations pour proposer des optimisations (jobs à créer, prompts à mémoriser, requêtes web problématiques). L’API `/learning/insights` regroupe ces données pour le Debug ou Task Hub.
- **Mode vocal** : websocket `/voice/stream` pour la console PySide6 (`desktop/voice_client`). Les journaux `app/logs/voice.asr.jsonl` sont consultables via `GET /voice/logs` pour auditer latence VAD/ASR. Utilisez `scripts/start-menu.bat` option `[14]` pour installer les dépendances (`.[voice]`) et `scripts/install_voice_resources.py` pour les modèles ASR/TTS (faster-whisper + Piper Jessica UPMC).
- **Recherche web contextuelle** : `app/core/websearch.py` filtre les requêtes superficielles (quoi/quel) et normalise le texte (stop words FR, garde sémantique) avant d’interroger DuckDuckGo (`ddgs`/`lite`). Les retours détaillés sont accessibles via `/debug/search`.
- **Orchestrateur de jobs** : création/édition des jobs (LLM, backup, RAG, plugin) depuis `/jobs`, duplication, suivi des exécutions (`/jobs/{id}/runs`) avec historisation (succès/échec) et prompts utilisés (`app/core/prompts.py` + `app/core/job_prompts.py`).
- **Console vocale avancée** : le dossier `desktop/voice_client/` fournit la base PySide6/QtQuick (capture micro, waveform animée, historique vocal, commandes assistées, TTS Piper). Le packaging autonome est disponible via `scripts/package_voice_client.py` ou le start-menu `[18]`.
- **Commandes système assistées** : la console PySide6 affiche les commandes JSON proposées par l’IA, demande confirmation selon le risque et journalise les rejets via `/commands/report` pour enrichir l’apprentissage.

## Tests & Qualité

- Lint/format : `uv run ruff check .`, `uv run black .`, `uv run isort .`.
- Tests : `uv run pytest -q` (API/LLM/RAG). Utilisez `uv run pytest --maxfail=1 tests/test_websearch.py` pour valider le filtrage sémantique.
- Les journaux métiers se trouvent dans `app/logs/` (server.jsonl, voice.asr.jsonl, audit.jsonl) et sont analysables via `/debug/logs` ou les scripts fournis.

## Documentation

- `docs/USER_GUIDE.md` : navigation UI (plugins, Jobs, Task Hub, mode vocal, auto-learning).
- `docs/API.md` : endpoints REST (auth, chat, jobs, prompts, learning, voice, commands).
- `docs/voice_client_overview.md` : architecture du client vocal, ressources audio, roadmap (Phases 1 à 5).

Consultez `scripts/` pour les utilitaires (installation modèle bge-m3, ressources vocales, tuning LLM, packaging client).
