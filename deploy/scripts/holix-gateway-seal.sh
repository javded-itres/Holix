#!/usr/bin/env bash
# Seal encrypted profile memory after gateway stop (systemd ExecStopPost).
set -euo pipefail

CONF="${HOLIX_SYSTEMD_CONF:-/etc/holix/holix.conf}"
if [[ -f "$CONF" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$CONF"
  set +a
fi

: "${HOLIX_BIN:?HOLIX_BIN must be set in holix.conf}"
: "${HOLIX_HOME:?HOLIX_HOME must be set in holix.conf}"

if [[ -z "${HOLIX_UNLOCK_KEY:-}" ]]; then
  if [[ -f "${HOLIX_HOME}/global/.env" ]]; then
    HOLIX_UNLOCK_KEY="$(grep -E '^HOLIX_UNLOCK_KEY=' "${HOLIX_HOME}/global/.env" | cut -d= -f2- | tr -d "\"'")"
    export HOLIX_UNLOCK_KEY
  fi
fi

if [[ -z "${HOLIX_UNLOCK_KEY:-}" ]]; then
  echo "holix-gateway-seal: HOLIX_UNLOCK_KEY not set; skipping seal" >&2
  exit 0
fi

exec "${HOLIX_BIN}" profile crypto seal --all --yes --unlock-key "${HOLIX_UNLOCK_KEY}"