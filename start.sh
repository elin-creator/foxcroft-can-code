#!/usr/bin/env bash
set -e

# Find where main.py lives
APP_DIR="$(dirname "$(readlink -f "$0")")"
echo "==> App directory: $APP_DIR"
echo "==> Contents:"
ls -la "$APP_DIR"

# Set working directory and Python path
cd "$APP_DIR"
export PYTHONPATH="$APP_DIR:$PYTHONPATH"

echo "==> PYTHONPATH: $PYTHONPATH"
echo "==> Starting uvicorn on port ${PORT:-8000}..."

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
