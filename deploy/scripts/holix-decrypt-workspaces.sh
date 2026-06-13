#!/usr/bin/env bash
# One-time migration: decrypt legacy encrypted workspace files for all profiles.
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
  echo "holix-decrypt-workspaces: HOLIX_UNLOCK_KEY not set; cannot decrypt" >&2
  exit 1
fi

export HOLIX_HOME
exec "${HOLIX_BIN}" profile crypto decrypt-workspace --all --yes --unlock-key "${HOLIX_UNLOCK_KEY}"