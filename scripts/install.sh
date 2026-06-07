#!/usr/bin/env bash
# Install Helix CLI for the current user (macOS / Linux).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "error: Python 3.14+ required" >&2
  exit 1
fi

exec "$PY" "$ROOT/scripts/install.py" "$@"