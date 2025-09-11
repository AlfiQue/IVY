# Repository Guidelines

## Project Structure & Module Organization
- `app/`: FastAPI app. Routers in `app/api/*`; services in `app/core/*` (LLM, security, plugins, rate limit, history, firewall, logger); entrypoint `app/cli.py`.
- `app/core/`: Configuration unifiée (`app/core/config.py`).
- `tests/`: Pytest suite (`tests/test_*.py`).
- `docs/`, `scripts/` (Windows `scripts/start-server.bat`), `config.json.example`, `pyproject.toml`.

## Build, Test, and Development Commands
- Install (editable + dev): `uv pip install -e .[dev]`
- Run locally: `uv run python -m app.cli serve` (host/port from `.env` or `config.json`).
- Tests: `uv run pytest -q` (coverage: `uv run pytest --cov=app --cov=core`).
- Lint/format: `uv run ruff check .`, `uv run black .`, `uv run isort .`.

## Coding Style & Naming Conventions
- Python 3.11; 4-space indent; type hints on public APIs.
- Formatting: Black (line length 88) and isort (profile "black").
- Linting: Ruff (target `py311`); keep `__all__` and imports clean.
- Names: files/modules `snake_case`; classes `PascalCase`; functions/vars `snake_case`; constants `UPPER_SNAKE`.

## Testing Guidelines
- Framework: pytest (+ `pytest-asyncio`). Place tests in `tests/` as `test_*.py`.
- Prefer small, deterministic tests; isolate filesystem/network; use fixtures for state.
- Name tests by behavior: `test_<unit>_<expected_behavior>()`.

## Commit & Pull Request Guidelines
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`). Imperative, concise subject.
- PRs: clear description, linked issues, steps to test, and screenshots/logs when useful. Update `docs/` for API or behavior changes.

## Security & Configuration Tips
- Configure via `.env` ou `config.json` (voir `app/core/config.py`). Exemple: `LLM_MODEL_PATH=models/llama-3.1-8b-instruct.Q5_K_M.gguf`.
- Outbound HTTP is allow-listed; use `FirewallHTTPClient` as an async context manager.
- Create `models/` at repo root and ensure the model file exists; install Tesseract if OCR is used.
