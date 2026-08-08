#!/usr/bin/env bash
# Install git hooks: ruff on commit + pre-push (must pass before git push).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if command -v uv >/dev/null 2>&1; then
  if ! uv run pre-commit --version >/dev/null 2>&1; then
    echo "Installing pre-commit via uv (dev group)…"
    uv sync --group dev 2>/dev/null || uv pip install pre-commit ruff
  fi
  PRE=(uv run pre-commit)
elif command -v pre-commit >/dev/null 2>&1; then
  PRE=(pre-commit)
else
  echo "ERROR: install pre-commit first:" >&2
  echo "  uv sync --group dev" >&2
  echo "  # or: pip install pre-commit ruff" >&2
  exit 1
fi

"${PRE[@]}" install --hook-type pre-commit --hook-type pre-push
echo "OK: pre-commit + pre-push hooks installed (ruff)."
echo "  commit: ruff --fix + format on staged files"
echo "  push:   ruff check + format --check on core cli api integrations tests"
echo
echo "Skip once (emergency only): git push --no-verify"
