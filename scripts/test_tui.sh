#!/usr/bin/env bash
# Full-launch Holix TUI tests (Textual Pilot, mock agent).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export HOLIX_AGENT_EXTENSIONS_OFF="${HOLIX_AGENT_EXTENSIONS_OFF:-1}"
exec uv run python -m pytest tests/tui -m tui -v --tb=short "$@"
