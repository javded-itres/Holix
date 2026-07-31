#!/bin/sh
set -e

export HOLIX_HOME="${HOLIX_HOME:-/data/.holix}"
export HOLIX_PROFILE="${HOLIX_PROFILE:-shared}"
export HOLIX_ENV="${HOLIX_ENV:-production}"

mkdir -p "$HOLIX_HOME" \
  "$HOLIX_HOME/extensions" \
  "$HOLIX_HOME/profiles" \
  "${HOLIX_FILES_DIR:-/data/files}"

# ---------------------------------------------------------------------------
# Optional: install / sync extensions via pip (HOLIX_EXTENSIONS_PIP)
# Specs are comma-separated: package names or paths visible in the container.
# ---------------------------------------------------------------------------
_install_extensions() {
  specs="${HOLIX_EXTENSIONS_PIP:-}"
  if [ -z "$specs" ]; then
    return 0
  fi
  sync="${HOLIX_EXTENSIONS_SYNC:-true}"
  marker="$HOLIX_HOME/.extensions-pip-installed"
  if [ "$sync" != "true" ] && [ "$sync" != "1" ] && [ -f "$marker" ]; then
    echo "[holix] extensions pip already installed (HOLIX_EXTENSIONS_SYNC=false)"
    return 0
  fi
  echo "[holix] Installing extensions: $specs"
  old_ifs=$IFS
  IFS=','
  # shellcheck disable=SC2086
  for spec in $specs; do
    spec=$(echo "$spec" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -z "$spec" ] && continue
    if [ -d "$spec" ] || [ -f "$spec" ]; then
      echo "[holix] uv pip install -e $spec"
      uv pip install -e "$spec" || {
        echo "[holix] WARN: failed to install $spec" >&2
        continue
      }
    else
      echo "[holix] uv pip install $spec"
      uv pip install "$spec" || {
        echo "[holix] WARN: failed to install $spec" >&2
        continue
      }
    fi
  done
  IFS=$old_ifs
  date -u +%Y-%m-%dT%H:%M:%SZ >"$marker" 2>/dev/null || true
}

# List drop-in extension roots for logs
_list_dropin_extensions() {
  root="$HOLIX_HOME/extensions"
  if [ ! -d "$root" ]; then
    return 0
  fi
  count=0
  for d in "$root"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    case "$name" in
      .* | __pycache__) continue ;;
    esac
    count=$((count + 1))
    echo "[holix] drop-in extension: $name"
  done
  if [ "$count" -eq 0 ]; then
    echo "[holix] no drop-in extensions under $root"
  fi
}

cmd="${1:-agent}"
shift || true

_install_extensions
_list_dropin_extensions

case "$cmd" in
  agent|full)
    # Gateway + Telegram/MAX companions (when tokens set) + cron
    uv run python scripts/docker_bootstrap.py
    exec uv run holix -p "$HOLIX_PROFILE" gateway start -f \
      --host "${HOLIX_GATEWAY_HOST:-0.0.0.0}" \
      --port "${HOLIX_GATEWAY_PORT:-8000}" \
      "$@"
    ;;
  gateway|gateway-only|api)
    # API gateway; companions controlled by HOLIX_TELEGRAM_AUTOSTART / HOLIX_MAX_AUTOSTART
    # For pure API, compose profile gateway-only sets autostart=false
    export HOLIX_TELEGRAM_AUTOSTART="${HOLIX_TELEGRAM_AUTOSTART:-true}"
    export HOLIX_MAX_AUTOSTART="${HOLIX_MAX_AUTOSTART:-true}"
    uv run python scripts/docker_bootstrap.py
    exec uv run holix -p "$HOLIX_PROFILE" gateway start -f \
      --host "${HOLIX_GATEWAY_HOST:-0.0.0.0}" \
      --port "${HOLIX_GATEWAY_PORT:-8000}" \
      "$@"
    ;;
  telegram)
    uv run python scripts/docker_bootstrap.py
    exec uv run holix -p "$HOLIX_PROFILE" telegram run "$@"
    ;;
  max)
    uv run python scripts/docker_bootstrap.py
    exec uv run holix -p "$HOLIX_PROFILE" max run "$@"
    ;;
  bootstrap)
    exec uv run python scripts/docker_bootstrap.py
    ;;
  extensions|ext)
    # Register / inspect: holix extensions …
    sub="${1:-list}"
    shift || true
    exec uv run holix -p "$HOLIX_PROFILE" extensions "$sub" "$@"
    ;;
  cli|helix|holix)
    exec uv run holix -p "$HOLIX_PROFILE" "$@"
    ;;
  shell|bash|sh)
    if [ "$#" -eq 0 ]; then
      exec /bin/bash
    fi
    exec "$@"
    ;;
  *)
    # Pass-through: docker run … holix-agent holix doctor
    if command -v "$cmd" >/dev/null 2>&1; then
      exec "$cmd" "$@"
    fi
    exec uv run holix -p "$HOLIX_PROFILE" "$cmd" "$@"
    ;;
esac
