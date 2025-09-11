# API

Authentification
- Login: `POST /auth/login` → cookie `access_token` (JWT) + JSON `{ csrf_token, session_id }`.
- Logout: `POST /auth/logout`
- CSRF: inclure `X‑CSRF‑Token` pour POST/PUT/DELETE.

Santé
- `GET /health` → `{ status, version, time, gpu, plugins_count, db_ok, faiss_ok }`

Plugins
- `GET /plugins` → `{ plugins: [{ name, state, meta }] }`
- `POST /plugins/{name}/enable|disable|start|stop|reload`
- `DELETE /plugins/{name}`
- `POST /plugins/upload` (multipart ZIP)

LLM
- `POST /llm/infer` → `{ text }` (non stream)
- `WS /llm/stream` (voir schéma WS ci‑dessous)

RAG
- `POST /rag/reindex { full?:bool=true }` → `{ indexed }`
- `POST /rag/query { query, top_k }` → `{ results: [{ text, score, source: { path, sha256, chunk_id, start, end } }] }`

Historique
- `POST /history/replay` (protégé CSRF)

Sessions
- `GET /sessions` → `{ sessions: [{ id, client, start_ts, last_activity, active }] }`
- `POST /sessions/{id}/terminate`

Jobs
- `GET /jobs` → liste
- `POST /jobs/add` → `{ id }`
- `GET /jobs/{id}` → détail (inclut `cancel_requested`)
- `POST /jobs/{id}/run-now`, `POST /jobs/{id}/update`, `POST /jobs/{id}/cancel`, `DELETE /jobs/{id}`

Sauvegardes
- `GET /backup/export` → ZIP (manifest/config/db/faiss/logs)
- `POST /backup/import?dry_run=true|false` (multipart ZIP) → `{ version, plan, dry_run }`

Schéma WebSocket (LLM)
- Messages JSON: `{ type, req_id, source, event, payload, ts }`
  - `type`: `event|error`
  - `event`: `token|status|error|end`
  - `payload`: texte ou info

Exemples
- cURL login:
```
curl -s -X POST http://127.0.0.1:8000/auth/login -H 'Content-Type: application/json' -d '{"user":"admin","password":"admin"}' -c cookies.txt
```
- cURL enable plugin:
```
curl -s -X POST http://127.0.0.1:8000/plugins/tasks/enable -b cookies.txt -H "X-CSRF-Token: <token>"
```
- WS (JavaScript):
```
const ws = new WebSocket('ws://127.0.0.1:8000/llm/stream');
ws.onopen = () => ws.send(JSON.stringify({type:'request',req_id:'1',source:'demo',event:'start',payload:{prompt:'Bonjour'},ts:Date.now()}));
ws.onmessage = ev => console.log(JSON.parse(ev.data));
```

Codes d’erreur
- 400: requête invalide; 401: non authentifié; 403: CSRF invalide; 404: ressource introuvable; 429: rate‑limit.
