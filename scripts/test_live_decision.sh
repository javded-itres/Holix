#!/usr/bin/env bash
# Live System One checks (nimble / jev). Not part of default CI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export HOLIX_DECISION_LIVE="${HOLIX_DECISION_LIVE:-1}"
export HOLIX_DECISION_BASE_URL="${HOLIX_DECISION_BASE_URL:-http://192.168.88.1:4000}"
export HOLIX_DECISION_MODEL="${HOLIX_DECISION_MODEL:-nimble}"

echo "Live decision tests"
echo "  HOLIX_DECISION_MODEL=${HOLIX_DECISION_MODEL}"
echo "  HOLIX_DECISION_BASE_URL=${HOLIX_DECISION_BASE_URL}"

exec .venv/bin/python -m pytest tests/live_llm/test_decision_live.py -m llm -vv --tb=short "$@"
