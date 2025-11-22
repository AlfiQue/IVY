# Sauvegarde et Restauration

Contenu du ZIP d’export (`GET /backup/export`)
- `manifest.json`: version de l’appli.
- `config.json` (si présent).
- `history.db` (SQLite événements).
- `faiss_index/` (index/faiss et méta RAG persistants).
- `logs/*.jsonl` (200 dernières lignes par fichier, minifiées).

Procédure
- Export (UI ou `ivy backup export` ou endpoint): récupérer le ZIP.
- Import (UI ou endpoint): `POST /backup/import?dry_run=true` pour voir le plan, puis `dry_run=false` pour appliquer.

Compatibilité versions
- Le `manifest.json` contient la version source. IVY tente de rester compatible; en cas d’évolution de schéma, migrez la base ou refaites un reindex RAG.

Sécurité & intégrité
- L’import effectue une extraction “safe” (protection zip‑slip) et restaure uniquement `config.json`, `history.db`, `faiss_index/*`, et copie les logs vers `app/logs/imported/`.
