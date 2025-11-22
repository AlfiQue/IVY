# Optimisation automatique des réglages LLM

Le script `scripts/auto_tune_llm.py` mesure la latence réelle de plusieurs valeurs pour un paramètre (ex. `llm_speculative_max_draft_tokens`) et sélectionne celle qui offre la meilleure performance. Il peut également appliquer automatiquement la valeur retenue à `config.json`.

## Exemple d’utilisation

```bash
.\.venv\Scripts\python.exe scripts\auto_tune_llm.py ^
    --param llm_speculative_max_draft_tokens ^
    --kind int ^
    --start 128 --stop 16 --step 16 ^
    --samples 3 ^
    --prompt "Explique en deux phrases comment calibrer un LLM local." ^
    --apply
```

- `--param` : clé `Settings` à optimiser. Par défaut `llm_speculative_max_draft_tokens`.
- `--kind` : `int` ou `float` selon le type du paramètre.
- `--start`, `--stop`, `--step` : valeurs explorées (descendantes). Même après avoir trouvé un bon réglage, le script continue à descendre pour vérifier qu’une valeur plus petite ne serait pas encore meilleure.
- `--samples` : nombre de runs par valeur (moyenne).
- `--prompt` : requête utilisée pour mesurer la latence.
- `--apply` : écrit la meilleure valeur directement dans `config.json` (active implicitement `llm_speculative_enabled` si besoin).

Chaque essai affiche les latences min/avg/max et un récapitulatif final indique la valeur retenue.  

> **Astuce** : on peut répéter l’opération avec d’autres paramètres (`llm_temperature`, `llm_max_output_tokens`, etc.) pour affiner le profil LLM.

## Script complet (multi-paramètres)

Pour enchaîner plusieurs optimisations et mesurer le gain global :

```bash
.\.venv\Scripts\python.exe scripts\auto_tune_llm_full.py ^
    --prompt "Explique en deux phrases comment optimiser un LLM local." ^
    --samples 2
```

- Mesure la latence initiale
- Optimise successivement : `llm_speculative_max_draft_tokens`, `llm_max_output_tokens`, `llm_temperature`, `llm_speculative_context_tokens`
- Applique chaque valeur gagnante à `config.json`
- Mesure la latence finale et affiche le gain estimé

Options utiles :

- `--skip PARAM` (répétable) pour ignorer un paramètre
- `--include-gpu-layers` pour ajouter `llm_n_gpu_layers` au plan
- `--config PATH` si le fichier de config n’est pas à la racine
