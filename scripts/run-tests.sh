#!/usr/bin/env bash
set -euo pipefail

COVERAGE=0
K_ARG=""
NOINSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--coverage) COVERAGE=1; shift ;;
    -k) shift; K_ARG="${1:-}"; shift || true ;;
    --no-install) NOINSTALL=1; shift ;;
    *) echo "Unknown option: $1"; echo "Usage: $0 [--coverage|-c] [-k pattern] [--no-install]"; exit 1 ;;
  esac
done

has() { command -v "$1" >/dev/null 2>&1; }

if [[ "$NOINSTALL" -eq 0 ]]; then
  if has uv; then
    uv pip install -e .[dev]
  elif has python; then
    python -m pip install --upgrade pip
    python -m pip install -e .[dev]
  else
    echo "Neither 'uv' nor 'python' found. Install uv (recommended) or Python 3.11+." >&2
    exit 1
  fi
fi

ARGS=()
if [[ "$COVERAGE" -eq 1 ]]; then
  ARGS+=("--cov=app" "--cov=core")
else
  ARGS+=("-q")
fi
if [[ -n "$K_ARG" ]]; then
  ARGS+=("-k" "$K_ARG")
fi

if has uv; then
  set -x
  uv run pytest "${ARGS[@]}"
else
  set -x
  python -m pytest "${ARGS[@]}"
fi

