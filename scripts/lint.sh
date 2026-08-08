#!/usr/bin/env bash
# Lint gate matching CI "Ruff" step. Used by pre-push hook.
#   ./scripts/lint.sh
#   ./scripts/lint.sh --fix
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGETS=(core cli api integrations tests)

run_ruff() {
  if command -v uv >/dev/null 2>&1 && [[ -d "$ROOT/.venv" ]]; then
    uv run ruff "$@"
  elif command -v ruff >/dev/null 2>&1; then
    ruff "$@"
  else
    echo "ERROR: ruff not found. Run: uv sync --group dev" >&2
    exit 1
  fi
}

if [[ "${1:-}" == "--fix" ]]; then
  echo "[lint] ruff check --fix ${TARGETS[*]}"
  run_ruff check --fix "${TARGETS[@]}"
else
  echo "[lint] ruff check ${TARGETS[*]}"
  run_ruff check "${TARGETS[@]}"
fi
echo "[lint] OK (same scope as CI)"
