# IVY Project Analysis for Gemini

This document provides a comprehensive overview of the IVY project, its architecture, and development conventions to be used as a context for Gemini.

## Project Overview

IVY is a local-first, private, and extensible AI assistant. Its core functionalities include:

*   **On-premise LLM:** Utilizes a local Large Language Model (Llama 3.1 8B Q5_K_M) for inference, ensuring data privacy.
*   **Local RAG:** Implements a Retrieval-Augmented Generation pipeline with OCR (Tesseract), embeddings (BGE-M3), and a FAISS vector store.
*   **Plugin Architecture:** Supports hot-swappable Python plugins for extending its capabilities.
*   **API and UI:** Exposes a FastAPI backend with a WebSocket for real-time communication, a web-based UI (React), and a desktop application (Tauri).
*   **Security:** Features JWT-based authentication, CSRF protection, rate limiting, and an outbound request firewall.

## Building and Running

### Backend (FastAPI)

1.  **Installation:**
    ```bash
    uv pip install -e .[dev]
    ```
2.  **Running:**
    ```bash
    uv run python -m app.cli serve
    ```

### Web UI (React)

1.  **Installation:**
    ```bash
    cd webui
    npm install
    ```
2.  **Running:**
    ```bash
    npm run dev
    ```

### Desktop App (Tauri)

1.  **Installation:**
    ```bash
    cd desktop
    npm install
    ```
2.  **Running:**
    ```bash
    npm run dev
    ```

## Development Conventions

### Python (Backend)

*   **Linting and Formatting:** The project uses `ruff`, `black`, and `isort` for code quality, enforced via `pre-commit` hooks.
*   **Testing:** Unit and integration tests are written with `pytest`. The test suite can be run with the `pytest` command.
*   **Dependencies:** Python dependencies are managed in `pyproject.toml`.

### Frontend (Web and Desktop)

*   **Linting and Formatting:** Both the `webui` and `desktop` projects use `eslint` and `prettier` for code quality.
*   **Scripts:** Key scripts for linting, formatting, and running the applications are defined in their respective `package.json` files.

### Commit Messages

The project follows the **Conventional Commits** specification for commit messages (e.g., `feat:`, `fix:`, `docs:`).

## Key Files and Directories

*   `app/`: The core FastAPI application.
    *   `main.py`: The application's entry point.
    *   `api/`: API route definitions.
    *   `core/`: Core application logic (config, security, LLM, etc.).
*   `docs/`: Project documentation.
*   `plugins/`: Directory for Python plugins.
*   `tests/`: Pytest test suite.
*   `webui/`: The React-based web user interface.
*   `desktop/`: The Tauri-based desktop application.
*   `pyproject.toml`: Python project configuration and dependencies.
*   `webui/package.json`: Web UI dependencies and scripts.
*   `desktop/package.json`: Desktop app dependencies and scripts.
