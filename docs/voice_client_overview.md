# IVY Voice Client Overview

This note summarizes the current structure of the new PySide6 voice client.
Later phases will extend each layer.

## Layout

- `desktop/voice_client/app.py`: PySide6 entry point.
- `desktop/voice_client/ui/`: Qt widgets and QML scene.
- `desktop/voice_client/audio/`: microphone capture, VAD, TTS and playback.
- `desktop/voice_client/services/`: REST/WebSocket communication with the IVY backend.
- `desktop/voice_client/state/`: global state (server status, history, pending commands).
- `desktop/voice_client/config/`: local settings (encrypted credentials, audio, cache).
- `desktop/voice_client/runtime/`: controller orchestrating audio capture/playback and future streaming.
- `desktop/voice_client/resources/`: audio models and sound assets.
- `scripts/install_voice_resources.py`: downloads ASR/TTS models.

## Quick install

1. Run `scripts/start-menu.bat`.
2. Choose option `[14]` pour installer les dépendances `voice` (PySide6, Piper, faster-whisper, etc.) puis télécharger les modèles audio.
3. Option `[18]` (ou `python scripts/package_voice_client.py`) génère un exécutable autonome dans `dist/voice_client/IVYVoice`.
4. Continue the development workflow from `desktop/voice_client`.

## Current capabilities

- Authentication via `/auth/login` (DPAPI decryption handled when credentials sont chiffrés).
- Microphone capture → WebSocket `/voice/stream` end-to-end, with transcript events renvoyés à l'interface (finale / partielle).
- Chaînage automatique transcription → requête `chat` (stub) → synthèse vocale (Piper) → lecture (pause/reprise/stop).
- Gestion d’un event loop asynchrone dédié pour orchestrer capture, streaming et TTS.
- Interface PySide6 avec statut, transcription, réponse et panneaux futuristes (placeholders animations/stats).
- Centre de commandes : lorsqu’un message IVY contient `commands`, la console affiche les actions proposées, évalue le risque et envoie les confirmations/rejets vers `/commands/ack` ou `/commands/report` (apprentissage).

## Next steps

1. Implémenter réellement `send_chat` (SSE/stream) et lier aux endpoints IVY existants.
2. Ajouter les animations avancées (waveform dynamique, radar de performances) et le statut serveur temps réel.
3. Gérer configuration complète (raccourcis, périphériques, cache) via une fenêtre dédiée.
4. Ajout d’un historique local synchronisé et d’un mode widget flottant.
5. Préparer le packaging Windows (PyInstaller/Nuitka) et la distribution auto-update.

## Phase tracking

- **Phase 1 (préparation)** : ce dépôt contient désormais la structure PySide6 complète, les dépendances `.[voice]`, les ressources ASR/TTS et le script d’installation (`scripts/install_voice_resources.py`).
- **Phase 2 (infrastructure audio)** : capture micro, VAD, streaming Whisper GPU et pipeline Piper sont fonctionnels (voir `desktop/voice_client/audio/*`).
- **Phase 3 (interfaces & états)** : l’UI QML/PySide6 expose déjà les panneaux statut/transcription, un widget d’historique et la configuration locale ; la gestion des raccourcis et du mode éco sera ajoutée dans les prochaines itérations.
- **Phase 4 (intégration serveur)** : le client REST/WebSocket communique avec IVY (`services/api_client.py`), gère l’auto-auth chiffrée et le cache local (dossiers `state/` & `config/`).
- **Phase 5 (commandes système & apprentissage)** : les événements sont stockés dans `app/data/learning_events.jsonl` et remontent dans Task Hub/Debug via `/learning/insights`, ce qui prépare la boucle d’apprentissage automatique des commandes.
