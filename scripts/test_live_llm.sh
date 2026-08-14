#!/usr/bin/env bash
# Run live LLM end-to-end scenarios (real provider traffic).
# Excluded from default CI (marker: live_llm / llm).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export HOLIX_LIVE_LLM="${HOLIX_LIVE_LLM:-1}"
export HOLIX_AGENT_EXTENSIONS_OFF="${HOLIX_AGENT_EXTENSIONS_OFF:-1}"

# Prefer Holix LiteLLM profile defaults when env not set
if [[ -z "${HOLIX_LIVE_BASE_URL:-}" && -f "${HOME}/.holix/global/.env" ]]; then
  # shellcheck disable=SC1090
  set -a && source "${HOME}/.holix/global/.env" && set +a
  if [[ -n "${LITELLM_API_BASE:-}" && -n "${LITELLM_API_KEY:-}" ]]; then
    export HOLIX_LIVE_BASE_URL="${HOLIX_LIVE_BASE_URL:-https://llm.it-rs.ru/v1}"
    export HOLIX_LIVE_API_KEY="${HOLIX_LIVE_API_KEY:-$LITELLM_API_KEY}"
    export HOLIX_LIVE_MODEL="${HOLIX_LIVE_MODEL:-smart}"
  fi
fi

echo "Live LLM tests — provider probe uses HOLIX_LIVE_* or holix settings"
echo "  HOLIX_LIVE_MODEL=${HOLIX_LIVE_MODEL:-"(from settings)"}"
echo "  HOLIX_LIVE_BASE_URL=${HOLIX_LIVE_BASE_URL:-"(from settings)"}"
echo "  HOLIX_LIVE_KEEP_ARTIFACTS=${HOLIX_LIVE_KEEP_ARTIFACTS:-0}"
echo

# Browser env for live_42 (best-effort)
uv run python -m playwright install chromium >/dev/null 2>&1 || true

exec uv run python -m pytest tests/live_llm -m live_llm -vv --tb=short "$@"
