# Guide Utilisateur

## Connexion & sécurité
- Page d’accueil : formulaire de connexion (admin par défaut). Une fois authentifié, le serveur place un cookie JWT HttpOnly et renvoie un `csrf_token` à utiliser dans `X-CSRF-Token` pour toute requête mutative.
- Réinitialisation du compte admin : créer le fichier `app/data/reset_admin.flag` puis redémarrer le serveur (`python -m app.cli serve`). Le mot de passe temporaire est affiché en console et journalisé.

## Navigation principale
| Section | Rôle |
|---------|------|
| **Chat** | Interface de conversation continue (volet gauche : conversations, volet central : messages). Chaque réponse affiche sa provenance (`LLM`, `Mémoire`, `Internet`). |
| **Mémoire** | Tableau des Q/R mémorisées (recherche, édition, suppression, import/export, test LLM/heuristique avec mise à jour du flag "variable"). |
| **Ollama** | Contrôles du serveur Ollama local (statut, start/stop, PID, version, journal). |
| **Debug** | Formulaire pour tester la recherche DuckDuckGo (retours formatés). |
| **Jeedom** | Indique si l’URL/API key sont configurées (intégration à venir). |
| **Jobs** | Programmation (jobs `llm` ou `backup`). L’option "plugin" a été retirée. |
| **Historique** | Consultation des événements (`/history`) avec pagination et détail JSON. |
| **Configuration** | Aperçu des paramètres (`config.json` + `.env`) : hôte/port, allowlist réseau, RAG, mémoire/LLM/Jeedom. |
| **Sauvegardes** | Export/impor zip (base, index FAISS, logs optionnels). |
| **API Keys** | Gestion des clés d’accès (scopes : `chat`, `memory`, `debug`, `jobs`, `history`, etc.). |

Les pages "Plugins" et "LLM" de l’ancienne version ont disparu au profit de ces nouveaux écrans.

## Fonctionnement du chat
1. Posez une question depuis l’UI (ou via `POST /chat/query`).
2. Le serveur récupère l’historique de la conversation, cherche des Q/R similaires, puis classe la question (variable? recherche web?).
3. Si la réponse existe en mémoire et n’est pas variable → réponse immédiate.
4. Sinon :
   - Recherche DuckDuckGo si nécessaire.
   - Generation via le LLM (llama.cpp par defaut) avec le contexte. Activez TensorRT-LLM si configure.
   - Sauvegarde question/réponse + métadonnées dans la base.
5. L’UI actualise la vue ; la provenance est affichée sur chaque message.

## Configuration à connaître (`config.json` ou variables d’environnement)
- `chat_system_prompt`, `chat_history_max_messages`, `qa_similarity_threshold`.
- `embedding_model_name` (modèle sentence-transformers téléchargé au premier lancement).
- `duckduckgo_safe_search`, `duckduckgo_region`, `duckduckgo_max_results`.
- `llm_provider` ("llama_cpp" par defaut ou "tensorrt_llm"), `llm_model_path`, `tensorrt_llm_*` pour pointer vers votre serveur TensorRT-LLM.
- `jeedom_base_url`, `jeedom_api_key` (placeholder pour les futures commandes domotiques).
- Les paramètres historiques (RAG, rate limit, logs, etc.) restent inchangés.

## Supervision & maintenance
- `/health` affiche désormais `conversations_total` et `qa_total` (plus de compteur de plugins).
- Les journaux sont dans `app/logs/*.jsonl`. Les services TensorRT-LLM conservent leurs journaux côté GPU.
- La base SQLite se trouve dans `app/data/history.db`. Pour repartir de zéro :
  ```bash
  python -m app.cli serve  # s’assure que le schéma est créé
  python - <<'PY'
  import asyncio
  from app.core import chat_store
  asyncio.run(chat_store.clear_all())
  PY
  ```
- Sauvegardes : utilisez `/backup/export` (UI ou API) ; pour restaurer, importez l’archive ZIP via l’écran Sauvegardes.

## Lignes de commande utiles
```bash
# Démarrer le serveur
python -m app.cli serve

# Servir l’UI buildée sur un port distinct
python -m app.cli ui --path webui/dist --port 5174

# Exécuter un job LLM ponctuel (exemple)
python -m app.cli task add llm --params '{"prompt": "Bonjour"}'
```

## Conseils PWA & bureau
- L’UI reste installable en PWA (manifest + service worker). Rafraîchir deux fois ou désinstaller/réinstaller la PWA pour forcer une mise à jour du cache.
- Le dossier `desktop/` contient toujours l’app Tauri (STT/TTS). Les mises à jour sont servies depuis `/updates/desktop/` comme auparavant.

## Tests recommandés
Après installation (`py -m pip install -r scripts/requirements-dev-no-llama.txt`) :
```bash
py -m pytest tests/test_chat_api.py tests/test_history_api.py tests/test_health.py -q
```
Ces tests vérifient la mémoire conversationnelle, l’API historique et la santé du service.

## Ce qui a changé par rapport aux plugins
- Plus de répertoire `plugins/` ni de CLI "plugin".
- Les automatismes doivent passer par la mémoire, le moteur de conversation ou des jobs programmés.
- DuckDuckGo et llama.cpp sont intégrés nativement; TensorRT-LLM est supporté en option ; les extensions futures (Jeedom, etc.) reposeront sur cette base.
