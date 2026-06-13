#!/usr/bin/env bash
# Create a single system user ``holix`` and lock down HOLIX_HOME (not per-profile users).
set -euo pipefail

HOLIX_USER="${HOLIX_USER:-holix}"
HOLIX_GROUP="${HOLIX_GROUP:-holix}"
HOLIX_HOME="${HOLIX_HOME:-/var/lib/holix}"
INSTALL_DIR="${HOLIX_INSTALL_DIR:-/opt/holix}"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: setup-holix-runtime-user.sh [options]

Options:
  --holix-home PATH     Data directory (default: /var/lib/holix)
  --install-dir PATH    Code checkout with .venv (default: /opt/holix)
  --existing-home PATH  Use an existing HOLIX_HOME (e.g. /home/itadmin/.holix)
  --dry-run             Print actions without executing
  -h, --help            Show this help

Creates one system user (holix) that owns HOLIX_HOME. Deploy/admin users keep
code access but lose read access to profile data unless they use sudo -u holix.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --holix-home)
      HOLIX_HOME="$2"
      shift 2
      ;;
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --existing-home)
      HOLIX_HOME="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

if ! id -u "$HOLIX_USER" >/dev/null 2>&1; then
  run sudo useradd \
    --system \
    --home-dir "$HOLIX_HOME" \
    --shell /usr/sbin/nologin \
    "$HOLIX_USER"
else
  echo "User $HOLIX_USER already exists"
fi

run sudo mkdir -p "$HOLIX_HOME" "$INSTALL_DIR"
run sudo chown -R "${HOLIX_USER}:${HOLIX_GROUP}" "$HOLIX_HOME"
run sudo chmod 700 "$HOLIX_HOME"

if [[ -d "${HOLIX_HOME}/profiles" ]]; then
  run sudo find "${HOLIX_HOME}/profiles" -type d -exec chmod 700 {} +
  run sudo find "${HOLIX_HOME}/profiles" -type f -exec chmod 600 {} +
fi

if [[ -d "${HOLIX_HOME}/.runtime-cache" ]]; then
  run sudo chown -R "${HOLIX_USER}:${HOLIX_GROUP}" "${HOLIX_HOME}/.runtime-cache"
  run sudo chmod -R u=rwX,go= "${HOLIX_HOME}/.runtime-cache"
fi

run sudo install -d -m 755 /etc/holix
if [[ ! -f /etc/holix/holix.conf ]]; then
  if [[ -f "${INSTALL_DIR}/deploy/systemd/holix.conf.example" ]]; then
    run sudo cp "${INSTALL_DIR}/deploy/systemd/holix.conf.example" /etc/holix/holix.conf
  fi
fi

run sudo install -m 755 "${INSTALL_DIR}/deploy/scripts/holix-gateway-seal.sh" /usr/local/bin/holix-gateway-seal.sh

cat <<EOF

Done. Next steps:
  1. Edit /etc/holix/holix.conf (HOLIX_PYTHON, HOLIX_BIN, HOLIX_HOME=${HOLIX_HOME})
  2. Install systemd unit: deploy/systemd/holix-gateway.service
  3. sudo systemctl daemon-reload && sudo systemctl enable --now holix-gateway

Gateway runs as user: ${HOLIX_USER}
Data directory: ${HOLIX_HOME}
EOF