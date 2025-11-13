# Mémoire conversationnelle & intégrations IVY

Ce document décrit le fonctionnement du mode "assistant conversationnel" introduit dans IVY, le stockage associé et les intégrations externes.

## Vue d’ensemble
1. **Question utilisateur** (UI ou API `/chat/query`).
2. **Recherche mémoire** :
   - embeddings (Sentence-Transformers `all-MiniLM-L6-v2`) et similarité cosine.
   - réponse identique non variable → réponse directe + exécution éventuelle (ex : commande Jeedom quand elle sera branchée).
3. **Classification** : heuristique locale + LLM TensorRT pour décider si la réponse est variable et/ou si une recherche web est nécessaire.
4. **Recherche web** : DuckDuckGo (`duckduckgo-search 5.3.0`) quand `needs_search = True` (résumés injectés au prompt).
5. **Génération** : LLMClient TensorRT-LLM produit la réponse finale.
6. **Sauvegarde** : stockage question/réponse + métadonnées (source, classification, résultats web) dans `qa_entries` et `messages`.
7. **Restitution** : retour API + enregistrement UI (message => balises de provenance LLM/base/index).

## Stockage SQLite (`app/data/history.db`)
| Table | Rôle | Champs clés |
|-------|------|-------------|
| `conversations` | sessions persistantes | `title`, `updated_at` |
| `messages` | historiques question/réponse | `role`, `origin`, `is_variable`, `metadata` |
| `qa_entries` | base de connaissances (Q/R) | `is_variable`, `origin`, `embedding`, `metadata`, `usage_count` |
| `qa_entries_fts` | index FTS5 pour recherche plein texte | (maintenu via triggers) |

### Méthodes utiles (`app/core/chat_store.py`)
- `ensure_conversation`, `add_message`, `similar_questions`, `save_qa`, `update_qa`, `list_qa`, `import_qa`, `export_qa`.
- `clear_all()` : purge les données tout en conservant le schéma.
- `init_db()` : création / migrations simples (appelé au start).

## API
- `POST /chat/query` : point d’entrée conversationnel (param `conversation_id` optionnel).
- `GET /chat/conversations` / `POST` / `PATCH` / `DELETE` : gestion basique des conversations.
- `GET /chat/conversations/{id}/messages` : pagination ordonnée.
- `GET|PATCH|DELETE /memory/qa/{id}` : CRUD base de Q/R.
- `POST /memory/qa/{id}/classify/{llm|heuristic}` : détermine la variabilité et met à jour la fiche.
- `POST /memory/qa/import` / `GET /memory/qa/export` : import/export JSON (embeddings retirés côté export API).
- `GET /debug/search` : tests DuckDuckGo.
- `GET /jeedom/status` : placeholder (base URL + API key depuis la config).

Toutes ces routes sont également exposées côté UI (`webui/src/api/client.ts`).

## UI (WebUI)
- **Chat** : interface principale (colonnes conversations/messages) avec badges d’origine (`LLM`, `Mémoire`, `Internet`).
- **Mémoire** : tableau Q/R (filtre plein texte, édition, tests LLM/heuristique, import/export).
- **Debug** : formulaire DuckDuckGo.
- **Jeedom** : état de configuration (intégration à venir).

Les autres sections (Jobs, Backups, Config, etc.) restent disponibles, mais la page "Plugins" a été retirée.

## Configuration (`app/core/config.py`)
Paramètres notables :
- `chat_system_prompt`, `chat_history_max_messages`, `qa_similarity_threshold`.
- `embedding_model_name` (par défaut `sentence-transformers/all-MiniLM-L6-v2`).
- `duckduckgo_safe_search`, `duckduckgo_region`, `duckduckgo_max_results`.
- `llm_provider` ("llama_cpp" ou "tensorrt_llm"), `llm_model_path`, `tensorrt_llm_*` : configuration du connecteur LLM.
- `jeedom_base_url`, `jeedom_api_key` (placeholder).

## Tests
Les tests existants à exécuter en priorité (après installation `py -m pip install -r scripts/requirements-dev-no-llama.txt`) :
```bash
py -m pytest tests/test_chat_api.py tests/test_history_api.py tests/test_health.py -q
```
Ils couvrent :
- pipeline conversationnel (mémoire + classification monkeypatchée),
- API historique (filtrage),
- endpoint `/health` (compteurs conversations / QA).

## Intégrations futures
- **Jeedom** : la page et le module `routes_jeedom` fournissent la base pour dialoguer avec l’API (autorisation + commandes). À implémenter via `app/core/jeedom.py` et un client HTTP restreint.
- **Commandes locales** : le champ `origin` et la colonne `metadata` permettent de stocker la provenance (par ex. `command: jeedom.turn_on`).
- **Planification** : jobs `llm` ou `backup` disponibles via `/jobs`; suppression des jobs "plugin" hérités.

## Migration depuis l’ancien système de plugins
1. Supprimer ou archiver l’intégralité du dossier `plugins/` et la config associée.
2. Vérifier `config.json` pour retirer les champs `llm_default_allowed_plugins`/`llm_allow_all_plugins`.
3. Reposer sur la mémoire intégrée et les appels HTTP pour automatiser les actions (Jeedom, etc.).

Cette documentation remplace l’ancien guide des plugins et reflète le fonctionnement actuel d’IVY.
