# Plugins — API et Bonnes pratiques

Structure
- Chaque plugin vit dans `plugins/<nom>/plugin.py` et expose `plugin = Plugin()`.
- Métadonnées via `Plugin.meta` (dict):
  - `name`: nom logique
  - `description`: texte court
  - `permissions`: ex: `['net','fs_read']` (synonymes: `network`, `filesystem`, `fs_write`, `process`)
  - `inputs.schema`: classe Pydantic ou dict de champs (JSON Schema simplifié) pour valider les arguments.

Cycle de vie
- `start()` (optionnel): démarrage/allocations.
- `stop()` (optionnel): arrêt/nettoyage.
- `run(**kwargs)`: exécution.

Découverte/chargement
- Le chargeur scanne `plugins/`, importe `plugin.py`, lit `Plugin.meta`, valide `permissions` et `inputs.schema` (crée un modèle Pydantic si dict), et inscrit dans le `REGISTRY` (state=`disabled`).
- Hot‑reload: `plugins.reload(name)` réimporte le module et restaure si échec (rollback), avec crash‑dump.

Sécurité réseau et FS
- Réseau: toute requête sortante doit respecter l’allowlist (`allowlist_domains`). Utilisez le client fourni ou vérifiez l’hôte.
- FS: si écriture nécessaire, ajoutez `fs_write` dans `permissions` et limitez les chemins.
- Process: si vous lancez des sous‑processus, ajoutez `process` (justifiez le besoin).

Crash‑dump
- Toute exception inattendue capture stdout/stderr + traceback dans `app/logs/plugins/<name>-<timestamp>.log`.

Exemples
- weather: interroge Open‑Meteo (cache 10 min, timeout 5s), `permissions=['net','fs_read']`.
- search: DuckDuckGo (1er résultat), `permissions=['net','fs_read']`.
- system_info: renvoie OS/CPU/GPU/RAM.
- tasks: pont CRUD vers le scheduler (create/update/delete/run_now/list/get).
- llm: appelle `LLM().infer(prompt, options)` (local, pas de net).

Squelette (scaffold)
- `python -m app.cli plugin scaffold monplugin` → crée `plugins/monplugin/plugin.py` depuis `plugins/_template/plugin.py`.

Bonnes pratiques
- Validez strictement les entrées (Pydantic).
- Timeout et gestion d’erreurs claires: retournez `{ "error": "..." }` plutôt qu’une exception non gérée.
- Journalisez via `app/core/logger.py` si besoin (catégories: server, plugin, llm, audit).

