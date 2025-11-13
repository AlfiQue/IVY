# Documentation IVY

## Vue d'ensemble
IVY est désormais centré sur :
- une mémoire conversationnelle locale (SQLite + embeddings) accessible via `/chat` et `/memory`,
- un client LLM TensorRT-LLM (serveur NVIDIA externe),
- des intégrations réseau contrôlées (DuckDuckGo, futur Jeedom),
- une UI React (Chat, Mémoire, Debug, Jobs, Config, Sauvegardes, etc.).

## Fichiers principaux
- INSTALL.md : prérequis matériels/logiciels et configuration TensorRT-LLM.
- USER_GUIDE.md : usage quotidien (UI, configuration, sauvegardes).
- PLUGINS.md : désormais guide "Mémoire & intégrations" (pipeline, API, migration).
- API.md : endpoints REST/WS actualisés (chat, mémoire, debug, etc.).
- DEVS.md : démarrage développeur (backend/frontend, modules clés, qualité, tests).
- manual/quickstart.md : aide-mémoire installation/test rapide.
- BACKUP_RESTORE.md, SECURITY.md, OCR.md : compléments thématiques.
- TENSORRT_LLM.md : compilation, conversion et lancement d'un serveur TensorRT-LLM.

## Captures d’écran
Déposez les images à jour dans `docs/img/` puis référencez-les (ex. `![Chat](img/chat.png)`).

## Bonnes pratiques
- Utiliser `config.json.example` comme base (prompts, embeddings, DuckDuckGo, LLM local (llama.cpp) ou TensorRT-LLM, Jeedom).
- Tests rapides : `py -m pytest tests/test_chat_api.py tests/test_history_api.py tests/test_health.py -q`.
- Supprimer l’ancien dossier `plugins/` et ses références : l’architecture est désormais pilotée par les modules `chat_store`/`chat_engine`.

Bonne lecture !
