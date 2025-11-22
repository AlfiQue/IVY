Changelog

v0.2 (Security, Robustness, Polish)
- Trace/Correlation ID: HTTP middleware (X-Trace-Id), JSONL logs, WS errors include trace_id.
- Auth security: JWT cookie HttpOnly + SameSite=Lax (+Secure in HTTPS), CSRF rotated per session_id.
- Anti brute-force: cooldown after 5 failures (429), retry_after_sec in details.
- Standard error codes (IVY_XXXX) for LLM input, WS auth, generic server errors.
- Firewall: allowlist domains + ports (80/443 by default).
- LLM: input/output limits (IVY_4101), max_tokens enforced in REST; WS requires auth.
- Plugins: execution timeout (30s), RAM cap (512MB), improved crash-dumps; secure ZIP upload + checksum.
- History: GET /history (pagination/filters), UI page; (masking/purge parameters available).
- Observability: optional /metrics (Prometheus).
- DX: .env.example extended; deps added (docx/xlsx/pptx, pyzipper, prometheus-client, psutil, tzdata, dotenv).
- UI/Desktop: ESLint/Prettier added; docs updated (PWA/Quality/Dev).

v0.1 (MVP)
- Backend FastAPI, Plugins, LLM WS, RAG, Scheduler, Backups, UI (React), Desktop Tauri (STT/TTS), tests and docs.
