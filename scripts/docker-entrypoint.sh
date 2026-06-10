#!/bin/sh
set -e

export HELIX_HOME="${HELIX_HOME:-/data/.helix}"
export HELIX_PROFILE="${HELIX_PROFILE:-default}"
export HELIX_ENV="${HELIX_ENV:-production}"

mkdir -p "$HELIX_HOME"

cmd="${1:-gateway}"
shift || true

case "$cmd" in
  gateway)
    uv run python scripts/docker_bootstrap.py
    exec uv run helix gateway start -f \
      --host "${HELIX_GATEWAY_HOST:-0.0.0.0}" \
      --port "${HELIX_GATEWAY_PORT:-8000}" \
      "$@"
    ;;
  telegram)
    uv run python scripts/docker_bootstrap.py
    exec uv run helix telegram run "$@"
    ;;
  cli|helix)
    exec uv run helix "$@"
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