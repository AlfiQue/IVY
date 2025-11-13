# Quickstart

## Installation standard
```
py -m pip install -e .[dev]
```

## Variante minimale
```
py -m pip install -r scripts/requirements-dev-no-llama.txt
```

## Lancement du serveur
```
python -m app.cli serve
```

## Tests ciblés
```
py -m pytest tests/test_chat_api.py tests/test_history_api.py tests/test_health.py -q
```

## Accès UI
Rendez-vous sur http://127.0.0.1:8000/admin (identifiants par défaut : admin / admin).
