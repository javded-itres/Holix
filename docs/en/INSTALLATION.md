# Installation

Holix requires **Python 3.12+** and installs as the CLI command **`holix`**. Pick one path below.

## Choose your path

| Path | Best for | Result |
|------|----------|--------|
| **A — Local (uv / pipx)** | Daily use, development, TUI, multi-profile on your machine | `holix` on the host; data in `~/.holix/` (or `%LOCALAPPDATA%\Holix\`) |
| **B — Docker** | Server, Telegram-first, minimal host dependencies | Container with gateway + Telegram + cron in one process |

After either path, continue with [START_HERE.md](START_HERE.md) for first-run checklist.

---

## Requirements (both paths)

| Requirement | Notes |
|-------------|--------|
| Python 3.12+ | Path A only (on the host) |
| [uv](https://github.com/astral-sh/uv) | **Recommended** for Path A — installs, sync, `uv tool install`, `uv run` |
| LLM endpoint | OpenAI-compatible API (Ollama, LiteLLM, OpenAI, Groq, …) |

### Optional extras (Path A)

| Extra | PyPI | From source (`uv sync`) | Enables |
|-------|------|-------------------------|---------|
| `telegram` | `pip install "Holix[telegram]"` | `--extra telegram` | `holix telegram`, gateway bot |
| `browser` | `pip install "Holix[browser]"` | `--extra browser` | Playwright — [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |
| `voice` | `pip install "Holix[voice]"` | `--extra voice` | Whisper in Telegram |
| `tui-web` | `pip install "Holix[tui-web]"` | `--extra tui-web` | `holix tui --web` |
| `windows` | `pip install "Holix[windows]"` | `--extra windows` | `psutil` process cleanup |
| `all` | `pip install "Holix[all]"` | `--extra all` | all of the above |

After `browser`: `playwright install chromium`

Package on PyPI: **[Holix](https://pypi.org/project/Holix/)** — name is `Holix`, CLI command is `holix`. Do **not** run `pip install helix` (unrelated package).

---

## Path A — Local install

### A1 — uv tool install (recommended)

Global `holix` without managing a venv manually:

```bash
uv tool install Holix
# with extras (Telegram needs aiogram):
uv tool install "Holix[all]"

holix version
holix bootstrap
holix doctor
```

Upgrade later: `uv tool upgrade Holix` or `holix update --channel pypi`.

### A2 — One-line installer (curl)

macOS/Linux: language detection, full/minimal choice, PyPI install, `holix bootstrap`:

```bash
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
```

| Choice | Package | Includes |
|--------|---------|----------|
| **Full** (default) | `Holix[all]` | Telegram, browser, voice, web TUI |
| **Minimal** | `Holix` | Core CLI, TUI, gateway, MCP |

Bootstrap configures locale, LLM provider, optional Telegram. Re-run:

```bash
HOLIX_BOOTSTRAP_LANG=ru bash install.sh
holix bootstrap --lang en
holix bootstrap --skip-telegram
holix bootstrap -y
```

Details: [START_HERE.md](START_HERE.md#1-install).

### A3 — pipx or pip

```bash
pipx install Holix
# or: pipx install "Holix[all]"

holix version
holix bootstrap
```

Inside a virtualenv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install "Holix[telegram]"
holix doctor
```

User install (`~/.local/bin` must be on PATH):

```bash
pip install --user Holix
export PATH="$HOME/.local/bin:$PATH"
```

### A4 — Windows

Python 3.12+ from [python.org](https://www.python.org/downloads/) — check **Add python.exe to PATH**.

```powershell
uv tool install Holix
# or: pipx install Holix

holix version
holix doctor
```

From git: `.\scripts\install.ps1` — open a **new** PowerShell window after install.

| Item | Path |
|------|------|
| Holix home | `%LOCALAPPDATA%\Holix\` |
| Profiles | `%LOCALAPPDATA%\Holix\profiles\<name>\` |

Optional: `pip install "Holix[windows]"` for process-tree cleanup.

### A5 — From git (developers)

```bash
git clone https://github.com/javded-itres/Holix.git
cd Holix
uv sync
uv pip install -e .
cp .env.example .env
holix doctor
holix models setup
```

Run without global install:

```bash
uv run holix tui
uv run holix doctor
```

Or use the repo installer:

```bash
./scripts/install.sh
holix install --extra telegram
```

### Path A — first-time configuration

Usually done by `holix bootstrap` after install. Otherwise:

```bash
holix doctor
holix models setup
holix telegram setup    # optional
holix tui
```

Data: `~/.holix/` (Linux/macOS), `%LOCALAPPDATA%\Holix\` (Windows), or `HOLIX_HOME`.  
Config layers: [CONFIGURATION.md](CONFIGURATION.md). Logs: [LOGS.md](LOGS.md).

### Path A — updates

```bash
holix update --channel pypi
holix update --check
```

Or: `pipx upgrade Holix` / `uv tool upgrade Holix`

### Path A — uninstall

1. Remove the `holix` binary from PATH (`uv tool uninstall Holix`, `pipx uninstall Holix`, or delete shim).
2. Optionally delete `~/.holix/` (profiles, gateway state, logs).

---

## Path B — Docker

No Python on the host required. Image includes Telegram, voice, and browser extras.

Files:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Agent + optional Ollama + gateway-only profile |
| `docker-compose.prod.yml` | Bind-mount storage, always-restart, log rotation |
| `docker/env.example` | Full environment template → copy to `.env` |
| `./extensions/` | Drop-in extensions (mounted into the container) |

### B1 — Quick start (model + Telegram → working agent)

```bash
cp docker/env.example .env
# Edit at least:
#   TELEGRAM_BOT_TOKEN=123456789:AAH...
#   MODEL=gpt-4o-mini
#   BASE_URL=https://api.openai.com/v1
#   API_KEY=sk-...
#   HOLIX_API_KEY_PEPPER=$(openssl rand -hex 32)

docker compose up -d --build
# or with local Ollama:
# docker compose --profile ollama up -d --build
```

On first run Holix creates profile `shared` (production-safe; `default` is forbidden when `HOLIX_ENV=production`), writes LLM and Telegram settings under `HOLIX_HOME`, enables workspace jail, and starts **gateway + Telegram + cron**.

Gateway health: `http://127.0.0.1:8000/health`

### B2 — Approve Telegram users (multi-user)

Users send `/start` in Telegram. Approve from the container:

```bash
docker compose exec holix holix -p shared telegram requests list
docker compose exec holix holix -p shared telegram requests approve USER_ID --create-profile alice
# bind to an existing profile:
docker compose exec holix holix -p shared telegram requests approve USER_ID --profile existing
```

Each approved user gets an isolated profile under `profiles/<name>/` (memory, workspace, SOUL). Use a **named** bot host profile (`-p shared`).

### B3 — Gateway only (API, no messengers)

```bash
# HOLIX_TELEGRAM_AUTOSTART / HOLIX_MAX_AUTOSTART forced off
docker compose --profile gateway-only up -d holix-gateway
```

Same image and volumes; no Telegram/MAX OS companions. Useful behind Studio, mobile apps, or reverse proxy.

### B4 — Production multi-user (bind-mounted storage)

```bash
mkdir -p ./data/holix ./extensions ./data/files
# in .env (paths become bind mounts via docker-compose.yml):
#   HOLIX_DATA_DIR=./data/holix
#   HOLIX_EXTENSIONS_DIR=./extensions
#   HOLIX_FILES_DIR=./data/files
# plus secrets + MODEL + TELEGRAM_BOT_TOKEN
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

| Env / host path | Container | Content |
|-----------------|-----------|---------|
| `HOLIX_DATA_DIR` (default named volume `holix-data`) | `/data/.holix` | Profiles, memory, gateway state, telegram.env |
| `HOLIX_EXTENSIONS_DIR` (default `./extensions`) | `/data/.holix/extensions` | Drop-in / git-cloned extensions |
| `HOLIX_FILES_DIR` (default `./data/files`) | `/data/files` | Optional shared host files |

Per-user workspace: `$HOLIX_DATA_DIR/profiles/<user>/workspace/` (jail on by default via `HOLIX_WORKSPACE_JAIL=true`).

### B5 — Extensions (load & register)

**Drop-in (no rebuild):**

```bash
# clone or copy under ./extensions/
git clone <repo> ./extensions/my-billing
docker compose restart holix
docker compose exec holix holix extensions list
docker compose exec holix holix extensions agent-list
```

**Pip on start** (comma-separated specs in `.env`):

```bash
HOLIX_EXTENSIONS_PIP=some-pypi-package,/data/.holix/extensions/local-pkg
HOLIX_EXTENSIONS_SYNC=true   # reinstall each start; false after first install
```

Entrypoint installs specs, then Holix discovers entry points + folders. See [EXTENSIONS.md](EXTENSIONS.md).

### B6 — Environment variables (main)

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `MODEL`, `BASE_URL`, `API_KEY` | OpenAI-compatible LLM |
| `HOLIX_API_KEY_PEPPER` | **Required** production API key hashing |
| `HOLIX_PROFILE` | Bot host profile (default `shared`) |
| `HOLIX_ENV=production` | Named profiles, auth enforced |
| `HOLIX_WORKSPACE_JAIL` | Per-profile file jail (default `true`) |
| `HOLIX_TELEGRAM_AUTOSTART` | Start Telegram companion (`false` = gateway-only) |
| `HOLIX_MAX_AUTOSTART` | Start MAX polling companion |
| `HOLIX_EXTENSIONS_PIP` | Comma-separated pip/path specs at boot |
| `HOLIX_DATA_DIR` | Host path for `HOLIX_HOME` (prod compose) |

Full template: [`docker/env.example`](../../docker/env.example).

### B7 — What runs inside

Command `agent` (default): `holix gateway start -f` — gateway, Telegram/MAX when tokens set, cron, extension sidecars.

Commands: `agent` | `gateway` | `telegram` | `max` | `bootstrap` | `extensions` | `cli` | `shell`.

Production ops (systemd, TLS, encryption): [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Troubleshooting install

| Symptom | Action |
|---------|--------|
| `holix: command not found` | Path A: add `~/.local/bin` to PATH or re-run `uv tool install` / `pipx install` |
| Python version error | Install 3.12+; `uv python install 3.12` |
| Import errors after git pull | `uv sync && uv pip install -e .` or `holix update --force` |
| Doctor: missing provider | `holix models setup` or `holix doctor --fix` |
| Docker: bot not responding | Check token, `docker compose logs`, approve user with `telegram requests approve` |
| Windows: script blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).

## See also

- [START_HERE.md](START_HERE.md) — checklist after install
- [CONFIGURATION.md](CONFIGURATION.md) — `.env`, profiles, models
- [DEPLOYMENT.md](DEPLOYMENT.md) — systemd, reverse proxy, production
- [PYPI.md](PYPI.md) — publishing (maintainers)