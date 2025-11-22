# Guide Utilisateur

## Connexion et sécurité

- Connexion admin via l’UI (formulaire en haut). Le serveur place un cookie JWT HttpOnly et renvoie un `csrf_token`. Toutes les requêtes POST/PUT/DELETE doivent inclure `X-CSRF-Token`.
- Reset admin (mot de passe temporaire) : créer le fichier `app\data\reset_admin.flag` puis redémarrer (le mot de passe s’affiche en console et est journalisé).

## Pages UI (menu principal)

- **Plugins** : liste, activer/désactiver/démarrer/arrêter/recharger, upload ZIP. Les plugins réseau doivent être autorisés via `allowlist_domains`.
- **Task Hub (`/task-hub`)** : vue synthétique des jobs (LLM, RAG, backup, plugins), actions rapides (run/cancel), prochaines exécutions, KPI et panneau Auto-learning (prompts récents/favoris, jobs fiables, suggestions). Lien direct vers `/tasks` pour modifier les planifications et accéder à l’historique détaillé.
- **Jobs (`/jobs`)** : création/édition des jobs (LLM, backup, RAG full/incrémental, plugin), adoption de prompts (récents/favoris) et duplication.
- **Historique / Sessions / Système / Config / Sauvegardes** : identiques à la version précédente (API health, rejouer des événements, terminer une session, lire/écrire la configuration, exporter/importer un ZIP).
- **Debug** : onglet “Recherche web” pour tester DuckDuckGo (avec statut backend) et section “Insights auto-learning” listant requêtes, jobs fiables et événements récents.
- **Commande vocale** : dictée navigateur (Web Speech) qui envoie automatiquement la transcription au chat.

## PWA mobile

- L’UI est installable (manifest + service worker). Android/Chrome : “Ajouter à l’écran d’accueil”. iOS/Safari : “Partager → Sur l’écran d’accueil”.
- Mises à jour : forcer un rafraîchissement (Ctrl/Cmd+F5) ou supprimer/réinstaller la PWA pour nettoyer le cache. Possibilité d’“Unregister” le Service Worker depuis les outils dev du navigateur.

## Mode vocal & console PySide6

- Installer les dependances : scripts/start-menu.bat option [14] (equivaut a pip install -e .[voice] + scripts/install_voice_resources.py --all pour les modeles faster-whisper et Piper Jessica UPMC).
- Le client desktop/voice_client streame le micro via /voice/stream, declenche le job LLM associe puis lit la reponse (TTS Piper).
- L'API consigne chaque session dans app/logs/voice.asr.jsonl. Les metriques (duree d'enregistrement, latence post-VAD, flux en attente) sont disponibles via GET /voice/logs.
- Raccourcis : Ctrl+Espace lance ou arrete l'ecoute, Ctrl+E active le mode eco/VAD. Les commandes JSON renvoyees par l'IA ouvrent un dialogue de confirmation (gestion du risque) et peuvent etre envoyees vers /commands/report pour l'apprentissage.
- Packaging : scripts/start-menu option `[18]` (ou `python scripts/package_voice_client.py`) produit un exécutable autonome dans `dist/voice_client/IVYVoice`.

## Auto-learning

- L’API `/learning/insights` combine les tables SQLite (`learning_events`), les prompts JSON (`app/data/job_prompts.json`) et les “learning events” JSONL pour proposer :
  - Prompts récents/favoris à réutiliser.
  - Jobs fiables (taux de succès/échec) et suggestions d’actions (planifier un RAG, ajouter une réponse à la mémoire, etc.).
  - Top requêtes web, requêtes non résolues et événements récents (latence, recherches nécessaires).
- Task Hub et la page Debug consomment cet endpoint. Les actions (bouton “Rafraîchir” ou “Lancer”) utilisent les routes sécurisées `/jobs/*`.

## RAG local

- Dossiers surveillés : `rag_inbox_dir`, `rag_knowledge_dir`. L’index FAISS persiste dans `rag_index_dir`.
- OCR FR activable : `rag_enable_ocr=true`, langue multi : `rag_ocr_lang=fra+eng`.
- Reindexation : `POST /rag/reindex` (UI bouton). Requêtes : `POST /rag/query`.

## Pare-feu sortant

- Autorisez explicitement les domaines dans `allowlist_domains` (ex. `open-meteo.com`, `duckduckgo.com`). Les sous-domaines sont pris en charge.

## Captures d’écran / documentation

- Ajoutez vos visuels récents dans `docs/img/` (ex. `ui-taskhub.png`, `ui-voice-console.png`) et référencez-les dans `README.md`.
- Les guides complémentaires sont disponibles dans `docs/` (`API.md`, `PLUGINS.md`, `TENSORRT_LLM.md`, `voice_client_overview.md`, etc.).
