#!/usr/bin/env bash
# Lint gate matching CI "Ruff" step. Used by pre-push hook.
#   ./scripts/lint.sh
#   ./scripts/lint.sh --fix   # optional auto-fix
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGETS=(core cli api integrations tests)
FIX=()
if [[ "${1:-}" == "--fix" ]]; then
  FIX=(--fix)
fi

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

echo "[lint] ruff check ${FIX[*]:-} ${TARGETS[*]}"
run_ruff check "${FIX[@]}" "${TARGETS[@]}"
echo "[lint] OK (same scope as CI)"
