#!/usr/bin/env bash
set -euo pipefail

# Change to repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Select python
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python not found. Please install Python 3.10+." >&2
  exit 1
fi

# Create venv if missing
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi

# Use venv python
VENV_PY="$(pwd)/.venv/bin/python"

"$VENV_PY" -m pip install -U pip
"$VENV_PY" -m pip install -r requirements.txt

# Initialize .env from example if absent
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
fi

# Start backend
PORT="${API_PORT:-9001}"
exec "$VENV_PY" -m uvicorn app.main:app --app-dir src --reload --host 0.0.0.0 --port "$PORT"

