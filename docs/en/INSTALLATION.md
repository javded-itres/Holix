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

### B1 — Quick start

```bash
export TELEGRAM_BOT_TOKEN="123456789:AAH..."
docker compose up -d
```

On first run Holix bootstraps `HOLIX_HOME` inside the container and saves the bot token.

### B2 — Approve Telegram users

Users send `/start` in Telegram. Approve from the container:

```bash
docker compose exec holix holix -p shared telegram requests list
docker compose exec holix holix -p shared telegram requests approve USER_ID --create-profile alice
# bind to existing profile:
docker compose exec holix holix -p shared telegram requests approve USER_ID --profile existing
```

Use a **named** bot profile (`-p shared` or your bootstrap profile). Profile `default` is dev-only when `HOLIX_ENV=production`.

### B3 — Environment variables

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Required for Telegram bot |
| `MODEL`, `BASE_URL` | Cloud LLM instead of bundled Ollama |
| `HOLIX_API_KEY_PEPPER` | Production API key hashing |
| `HOLIX_ENV=production` | Production policy (named profiles) |

Bind `HOLIX_HOME` to a host volume to persist profiles across container restarts (see `docker-compose.yml` in the repo).

### B4 — What runs inside

`holix gateway start -f` — gateway, Telegram bot, and cron scheduler in one process.

Production layout (systemd, TLS, encryption): [DEPLOYMENT.md](DEPLOYMENT.md) — Docker section there points back here for install; DEPLOYMENT covers **operations**, not first-time container setup.

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