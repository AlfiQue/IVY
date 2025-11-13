# API

## Authentification
- `POST /auth/login` -> cookie `access_token` + JSON `{ csrf_token, session_id }`.
- `POST /auth/logout`
- Les requetes mutatives doivent inclure `X-CSRF-Token`.
- Les clients externes peuvent utiliser les API keys (`Authorization: Bearer <KEY>`), scopes disponibles : `chat`, `memory`, `debug`, `jobs`, `history`, `rag`, `backup`, `config`.

## Chat & Memoire
- `POST /chat/query { question, conversation_id? }` -> `{ conversation_id, origin, answer, question_message, answer_message, ... }`
- `GET /chat/conversations` / `POST` / `PATCH` / `DELETE`
- `GET /chat/conversations/{id}/messages`
- `GET /memory/qa` (pagination, recherche plein texte)
- `PATCH /memory/qa/{id}` / `DELETE`
- `POST /memory/qa/{id}/classify/llm|heuristic` (retourne la classification et, si update_flag=true, la fiche QA mise a jour)
- `POST /memory/qa/import` / `GET /memory/qa/export`

## Recherche Web
- `GET /debug/search?q=...` -> résultats DuckDuckGo (texte/titres/liens).

## Jeedom (placeholder)
- `GET /jeedom/status` -> `{ configured: bool, base_url }`

## Jobs / sauvegardes / RAG
- `GET /jobs`, `POST /jobs/add`, `GET /jobs/{id}`, `POST /jobs/{id}/run-now`, `POST /jobs/{id}/update`, `POST /jobs/{id}/cancel`, `DELETE /jobs/{id}` (types supportes : `llm`, `backup`).
- `GET /backup/export`, `POST /backup/import?dry_run=true|false`
- `POST /rag/reindex`, `POST /rag/query`

## Historique
- `GET /history?limit=&offset=&q=&event_type=` -> `{ items, total }`

## Sante
- `GET /health` -> `{ status, version, time, gpu, conversations_total, qa_total, db_ok, faiss_ok, cpu_percent, mem_percent, ... }`

## WebSocket (LLM streaming)
- Endpoint legacy conservé : `ws://<host>/llm/stream` avec messages `{ type, req_id, event, payload }`.

## Exemples
```
# Connexion
curl -s -X POST http://127.0.0.1:8000/auth/login -H 'Content-Type: application/json' -d '{"user":"admin","password":"admin"}' -c cookies.txt

# Requete chat
curl -s -X POST http://127.0.0.1:8000/chat/query -H 'Content-Type: application/json' -H "X-CSRF-Token: <token>" -b cookies.txt -d '{"question":"Bonjour"}'

# Liste memoire (API key scope memory)
curl -s -H 'Authorization: Bearer <KEY>' http://127.0.0.1:8000/memory/qa
```

## Codes d'erreur
- `400` : requete invalide
- `401` : non authentifie / cle invalide
- `403` : CSRF ou droits insuffisants
- `404` : ressource introuvable
- `429` : limite de requetes atteinte

