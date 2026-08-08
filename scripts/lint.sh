#!/usr/bin/env bash
# Same lint gate as CI / pre-push. Run before push if hooks are not installed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGETS=(core cli api integrations tests)

run_ruff() {
  if command -v uv >/dev/null 2>&1 && [[ -x "$ROOT/.venv/bin/ruff" || -d "$ROOT/.venv" ]]; then
    uv run ruff "$@"
  elif command -v ruff >/dev/null 2>&1; then
    ruff "$@"
  else
    echo "ERROR: ruff not found. uv sync --group dev  or  pip install ruff" >&2
    exit 1
  fi
}

echo "[lint] ruff check ${TARGETS[*]}"
run_ruff check "${TARGETS[@]}"
echo "[lint] ruff format --check ${TARGETS[*]}"
run_ruff format --check "${TARGETS[@]}"
echo "[lint] OK"
