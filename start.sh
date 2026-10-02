#!/usr/bin/env sh
# One-command start on macOS/Linux: sets up dependencies on first run, then serves on http://127.0.0.1:8000
set -e
cd "$(dirname "$0")"
PY=backend/.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "Creating Python environment..."
  python3 -m venv backend/.venv
  "$PY" -m pip install -q -r backend/requirements.txt
fi
if [ ! -f frontend/dist/index.html ]; then
  echo "Building the analyst console..."
  (cd frontend && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build)
fi
exec "$PY" run.py --open "$@"
