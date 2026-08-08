#!/usr/bin/env bash
# Install git hooks so ruff runs before every push (and on commit).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if command -v uv >/dev/null 2>&1; then
  uv sync --group dev >/dev/null 2>&1 || uv pip install pre-commit ruff
  if uv run pre-commit --version >/dev/null 2>&1; then
    PRE=(uv run pre-commit)
  else
    # ensure package is on PATH via venv
    if [[ -x "$ROOT/.venv/bin/pre-commit" ]]; then
      PRE=("$ROOT/.venv/bin/pre-commit")
    else
      uv pip install pre-commit
      PRE=("$ROOT/.venv/bin/pre-commit")
    fi
  fi
elif command -v pre-commit >/dev/null 2>&1; then
  PRE=(pre-commit)
else
  echo "ERROR: install pre-commit:" >&2
  echo "  uv sync --group dev && uv pip install pre-commit" >&2
  exit 1
fi

"${PRE[@]}" install --hook-type pre-commit --hook-type pre-push
echo "OK: hooks installed"
echo "  pre-commit: ruff --fix + format (staged files)"
echo "  pre-push:   ./scripts/lint.sh  →  ruff check core cli api integrations tests"
echo
echo "Manual: ./scripts/lint.sh"
echo "Skip once: git push --no-verify"
