#!/usr/bin/env bash
set -euo pipefail

NOINSTALL=0
SKIPCHECKS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-install) NOINSTALL=1; shift ;;
    --skip-checks) SKIPCHECKS=1; shift ;;
    *) echo "Unknown option: $1"; echo "Usage: $0 [--no-install] [--skip-checks]"; exit 1 ;;
  esac
done

has() { command -v "$1" >/dev/null 2>&1; }

if [[ "$NOINSTALL" -eq 0 ]]; then
  if has uv; then
    uv pip install -e .
  elif has python; then
    python -m pip install --upgrade pip
    python -m pip install -e .
  else
    echo "Neither 'uv' nor 'python' found." >&2
    exit 1
  fi
fi

if [[ "$SKIPCHECKS" -eq 0 ]]; then
  if has uv; then
    uv run python scripts/check_env.py
  else
    python scripts/check_env.py
  fi
fi

echo "Starting IVY server..."
if has uv; then
  uv run python -m app.cli serve
else
  python -m app.cli serve
fi

