# Sécurité

Modèle de menace (local)
- Usage LAN local; surface d’attaque: UI web, API HTTP, WS. Objectifs: éviter CSRF, limiter exfiltration réseau, cloisonner les plugins.

Mécanismes
- Authentification: JWT (cookie HttpOnly), expiration 12h.
- CSRF: `X‑CSRF‑Token` (itsdangerous), vérifié sur POST/PUT/DELETE.
- Rate‑limit: middleware global (par défaut 10 req/s, configurable).
- Pare‑feu sortant: allowlist de domaines (wildcards sous‑domaines).
- Audit: logger JSONL (catégories: server, plugin, llm, audit) avec rotation taille+temps.

Recommandations
- Restreindre `allowlist_domains` au strict nécessaire (ex: `api.open-meteo.com`, `api.duckduckgo.com`).
- Mettre un reverse proxy (Nginx/Traefik) en frontal si exposition WAN (auth complémentaire, TLS, headers de sécurité).
- Éviter `fs_write` et `process` dans les plugins sauf nécessité.
- Utiliser des comptes système limités/ACL appropriées pour les dossiers de données.

Reset admin
- Fichier drapeau: `C:\IVY\reset_admin.flag`. Au démarrage, un mot de passe temporaire est généré puis journalisé (audit) et affiché en console.

