#!/usr/bin/env bash
# Holix installer — one-liner from GitHub or local git clone.
#
#   curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh -o install.sh && bash install.sh
#
# From repository:
#   ./scripts/install.sh
set -euo pipefail

HOLIX_REPO="${HOLIX_REPO:-https://github.com/javded-itres/Holix.git}"
HOLIX_BRANCH="${HOLIX_BRANCH:-main}"
MIN_PY_MAJOR=3
MIN_PY_MINOR=12

INSTALL_LANG="${HOLIX_BOOTSTRAP_LANG:-}"

info() { printf '\033[1;34mℹ\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; }

SCRIPT_PATH="${BASH_SOURCE[0]:-}"
if [[ -n "$SCRIPT_PATH" && "$SCRIPT_PATH" != /dev/fd/* && "$SCRIPT_PATH" != /dev/stdin && "$SCRIPT_PATH" != - ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  SCRIPT_DIR=""
  REPO_ROOT=""
fi

is_repo_install() {
  [[ -n "$REPO_ROOT" && -f "$REPO_ROOT/pyproject.toml" ]] && grep -q 'name = "Holix"' "$REPO_ROOT/pyproject.toml" 2>/dev/null
}

find_python() {
  local candidates=()
  if command -v python3 >/dev/null 2>&1; then candidates+=("python3"); fi
  if command -v python >/dev/null 2>&1; then candidates+=("python"); fi
  for py in "${candidates[@]}"; do
    if "$py" -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= ($MIN_PY_MAJOR, $MIN_PY_MINOR) else 1)" 2>/dev/null; then
      echo "$py"
      return 0
    fi
  done
  return 1
}

detect_system_lang() {
  local raw="${LC_ALL:-${LC_MESSAGES:-${LANG:-${LANGUAGE:-}}}}"
  raw="${raw%%.*}"
  raw="${raw%%_*}"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  if [[ "$raw" == "ru" ]]; then
    echo ru
  else
    echo en
  fi
}

resolve_install_lang() {
  if [[ -n "$INSTALL_LANG" ]]; then
    return
  fi
  local system
  system="$(detect_system_lang)"
  if [[ "$system" == "ru" ]]; then
    INSTALL_LANG=ru
    return
  fi
  if [[ ! -t 0 ]]; then
    INSTALL_LANG=en
    return
  fi
  echo
  echo "Choose install language / Выберите язык установки:"
  echo "  1) English"
  echo "  2) Русский"
  local choice
  read -r -p "Language / Язык [1]: " choice
  case "${choice:-1}" in
    2|ru|RU|русский|Русский) INSTALL_LANG=ru ;;
    *) INSTALL_LANG=en ;;
  esac
}

msg() {
  local key="$1"
  case "$INSTALL_LANG" in
    ru)
      case "$key" in
        installer_title) printf '%s\n' "Установщик Holix" ;;
        python_needed) printf '%s\n' "Нужен Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+" ;;
        python_version) printf '%s\n' "Python" ;;
        full_install_prompt) printf '%s' "Полная установка? (Telegram, браузер, голос, web TUI) [Y/n]: " ;;
        installing) printf '%s\n' "Установка" ;;
        from_pypi) printf '%s\n' "из PyPI…" ;;
        pipx_missing) printf '%s\n' "pipx не найден — устанавливаем…" ;;
        pipx_failed) printf '%s\n' "Не удалось установить pipx" ;;
        installed) printf '%s\n' "Holix установлен" ;;
        from_sources) printf '%s\n' "Установка из исходников:" ;;
        bootstrap_start) printf '%s\n' "Первичная настройка (LLM, Telegram)…" ;;
        holix_missing) printf '%s\n' "holix не найден в PATH — пропускаем bootstrap" ;;
        holix_missing_hint) printf '%s\n' "Откройте новый терминал и выполните: holix bootstrap" ;;
        bootstrap_warn) printf '%s\n' "bootstrap завершился с кодом" ;;
      esac
      ;;
    *)
      case "$key" in
        installer_title) printf '%s\n' "Holix installer" ;;
        python_needed) printf '%s\n' "Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ required" ;;
        python_version) printf '%s\n' "Python" ;;
        full_install_prompt) printf '%s' "Full install? (Telegram, browser, voice, web TUI) [Y/n]: " ;;
        installing) printf '%s\n' "Installing" ;;
        from_pypi) printf '%s\n' "from PyPI…" ;;
        pipx_missing) printf '%s\n' "pipx not found — installing…" ;;
        pipx_failed) printf '%s\n' "Failed to install pipx" ;;
        installed) printf '%s\n' "Holix installed" ;;
        from_sources) printf '%s\n' "Installing from sources:" ;;
        bootstrap_start) printf '%s\n' "Initial setup (LLM, Telegram)…" ;;
        holix_missing) printf '%s\n' "holix not on PATH — skipping bootstrap" ;;
        holix_missing_hint) printf '%s\n' "Open a new terminal and run: holix bootstrap" ;;
        bootstrap_warn) printf '%s\n' "bootstrap exited with code" ;;
      esac
      ;;
  esac
}

prompt_full_install() {
  if [[ ! -t 0 ]]; then
    FULL_INSTALL=0
    return
  fi
  echo
  local prompt
  prompt="$(msg full_install_prompt)"
  read -r -p "$prompt" answer
  case "${answer:-Y}" in
    [Yy]|"") FULL_INSTALL=1 ;;
    *) FULL_INSTALL=0 ;;
  esac
}

ensure_path() {
  export PATH="$HOME/.local/bin:$PATH"
}

run_bootstrap() {
  local holix_bin=""
  holix_bin="$(command -v holix 2>/dev/null || true)"
  if [[ -z "$holix_bin" && -x "$HOME/.local/bin/holix" ]]; then
    holix_bin="$HOME/.local/bin/holix"
  fi
  if [[ -z "$holix_bin" && is_repo_install && -x "$REPO_ROOT/.venv/bin/holix" ]]; then
    holix_bin="$REPO_ROOT/.venv/bin/holix"
  fi
  if [[ -z "$holix_bin" ]]; then
    warn "$(msg holix_missing)"
    warn "$(msg holix_missing_hint)"
    return 0
  fi
  export HOLIX_BOOTSTRAP_LANG="$INSTALL_LANG"
  info "$(msg bootstrap_start)"
  "$holix_bin" bootstrap --lang "$INSTALL_LANG" || warn "$(msg bootstrap_warn) $?"
}

install_from_pypi() {
  local py
  py="$(find_python)" || { err "$(msg python_needed)"; exit 1; }
  info "$(msg python_version): $($py --version 2>&1)"

  prompt_full_install
  local spec="Holix"
  if [[ "$FULL_INSTALL" == 1 ]]; then
    spec="Holix[all]"
  fi

  info "$(msg installing) $spec $(msg from_pypi)"
  if command -v uv >/dev/null 2>&1; then
    uv tool install --force "$spec"
  elif command -v pipx >/dev/null 2>&1; then
    pipx install --force "$spec"
  else
    info "$(msg pipx_missing)"
    "$py" -m pip install --user pipx
    "$py" -m pipx ensurepath || true
    ensure_path
    if command -v pipx >/dev/null 2>&1; then
      pipx install --force "$spec"
    else
      err "$(msg pipx_failed)"
      exit 1
    fi
  fi

  ensure_path
  ok "$(msg installed)"
}

install_from_repo() {
  local py
  py="$(find_python)" || { err "$(msg python_needed)"; exit 1; }

  prompt_full_install
  local extras=()
  if [[ "$FULL_INSTALL" == 1 ]]; then
    extras+=(--extra all)
  fi

  info "$(msg from_sources) $REPO_ROOT"
  "$py" "$REPO_ROOT/scripts/install.py" "${extras[@]}"
}

echo
resolve_install_lang
info "$(msg installer_title)"
ensure_path

if is_repo_install; then
  install_from_repo
else
  install_from_pypi
fi

run_bootstrap