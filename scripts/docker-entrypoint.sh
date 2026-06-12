#!/bin/sh
set -e

export HOLIX_HOME="${HOLIX_HOME:-/data/.holix}"
export HOLIX_PROFILE="${HOLIX_PROFILE:-default}"
export HOLIX_ENV="${HOLIX_ENV:-production}"

mkdir -p "$HOLIX_HOME"

cmd="${1:-gateway}"
shift || true

case "$cmd" in
  gateway)
    uv run python scripts/docker_bootstrap.py
    exec uv run holix gateway start -f \
      --host "${HOLIX_GATEWAY_HOST:-0.0.0.0}" \
      --port "${HOLIX_GATEWAY_PORT:-8000}" \
      "$@"
    ;;
  telegram)
    uv run python scripts/docker_bootstrap.py
    exec uv run holix telegram run "$@"
    ;;
  cli|helix)
    exec uv run holix "$@"
    ;;
  bootstrap)
    exec uv run python scripts/docker_bootstrap.py
    ;;
  shell|bash|sh)
    exec "$@"
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac