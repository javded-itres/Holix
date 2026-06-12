# Installation

Holix targets **Python 3.12+** and is packaged as a Typer CLI (`holix`). Choose one of the paths below depending on whether you run from source or want a global command.

## Requirements

| Requirement | Notes |
|-------------|--------|
| Python | 3.12 or newer |
| [uv](https://github.com/astral-sh/uv) | Recommended for deps and `uv run` |
| LLM endpoint | OpenAI-compatible API (Ollama, LiteLLM, OpenAI, Groq, …) |

Optional extras (install when needed):

| Extra | PyPI (`pip` / `pipx`) | From source (`uv sync`) | Enables |
|-------|----------------------|-------------------------|---------|
| `telegram` | `pip install "Holix[telegram]"` | `uv sync --extra telegram` | `holix telegram`, gateway Telegram |
| `browser` | `pip install "Holix[browser]"` | `uv sync --extra browser` | Playwright tools — [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |
| `voice` | `pip install "Holix[voice]"` | `uv sync --extra voice` | Whisper voice notes in Telegram |
| `tui-web` | `pip install "Holix[tui-web]"` | `uv sync --extra tui-web` | `holix tui --web` |
| `windows` | `pip install "Holix[windows]"` | `uv sync --extra windows` | `psutil` process-tree cleanup |
| `all` | `pip install "Holix[all]"` | `uv sync --extra all` | all of the above |

After the `browser` extra: `playwright install chromium`

## Quick install (recommended for users)

### One-line install (curl)

The fastest path for macOS/Linux: download `install.sh`, detect UI language, choose install type, install from PyPI, then run interactive setup.

```bash
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
```

Or save and run:

```bash
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh -o install.sh
bash install.sh
```

**What the script does:**

1. **Language** — reads `LANG` / `LC_ALL` / `LC_MESSAGES`:
   - Russian system (`ru_*`) → installer and `holix bootstrap` use **Russian** automatically
   - English or other → prompts: `1) English` / `2) Русский`
2. **Install type** — full vs minimal (see table below)
3. **Package** — `pipx install` or `uv tool install` from PyPI
4. **Bootstrap** — `holix bootstrap`: LLM provider + optional Telegram (bot token, admin Telegram ID)

| Choice | PyPI package | Includes |
|--------|--------------|----------|
| **Full** (default) | `Holix[all]` | Telegram, browser, voice, web TUI |
| **Minimal** | `Holix` | Core CLI, TUI, gateway, MCP |

**Bootstrap (`holix bootstrap`)** after install:

| Step | Action |
|------|--------|
| Locale | Saves UI language to `profiles/default/data/locale.json` and `profiles/admin/data/locale.json` |
| LLM | Choose Ollama, LiteLLM, OpenAI, or Groq; probe connection; save to profile `config.yaml` |
| Telegram | Optional: bot token, your Telegram user ID as admin, `HOLIX_TELEGRAM_VOICE_LANGUAGE` |

Force language or re-run setup:

```bash
HOLIX_BOOTSTRAP_LANG=ru bash install.sh
holix bootstrap --lang en
holix bootstrap --skip-telegram
holix bootstrap -y          # non-interactive (skips prompts)
```

From a git clone, `./scripts/install.sh` uses the same flow (local `uv sync` + bootstrap).

### From PyPI (manual)

Published on [pypi.org/project/Holix](https://pypi.org/project/Holix/) (current: **0.1.11**).

Package name **`Holix`** (not `holix` — that name is used by another project).  
After install, the CLI command is **`holix`** in the environment’s `bin` directory.

**Global CLI from any folder** (recommended — no manual PATH):

```bash
pipx install Holix
# or:
uv tool install Holix

holix version
```

**Inside a virtualenv** (activate the venv, then `holix` works in any directory):

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install Holix
pip install "Holix[telegram,browser,tui-web]"
holix version
holix doctor
```

**User install without pipx** (`~/.local/bin` must be on your PATH):

```bash
pip install --user Holix
# macOS/Linux: ensure ~/.local/bin is in PATH, e.g. in ~/.zshrc:
#   export PATH="$HOME/.local/bin:$PATH"
holix version
```

See [PYPI.md](PYPI.md).

### From git

```bash
git clone https://github.com/javded-itres/Holix.git
cd Holix
./scripts/install.sh
# Windows: .\scripts\install.ps1
```

Or after you already have `holix` on PATH:

```bash
holix install
holix install --extra telegram
holix install --extra browser
holix install --system          # all users; may need sudo / Administrator
```

The installer:

- Detects the repo root and runs `uv sync` (with selected extras)
- Installs the package editable (`uv pip install -e .`)
- Adds `~/.local/bin` (or system path) to your shell PATH unless `--no-path`

Verify:

```bash
holix version
holix doctor
```

## Windows

**Requirements:** Python 3.12+ from [python.org](https://www.python.org/downloads/) (check “Add python.exe to PATH” during setup).  
**Recommended:** [uv](https://github.com/astral-sh/uv) for dependencies.

### Global `holix` from any folder

**PyPI (simplest):**

```powershell
pipx install Holix
# or:
uv tool install Holix

holix version
holix doctor
```

**From git clone:**

```powershell
git clone https://github.com/javded-itres/Holix.git
cd Holix
.\scripts\install.ps1
# or, if holix is already on PATH:
holix install --extra telegram
```

The installer adds Holix to your user PATH. **Open a new PowerShell window** after install, then run `holix version`.

### Data and profiles

| Item | Path |
|------|------|
| Holix home | `%LOCALAPPDATA%\Holix\` (or `HOLIX_HOME`) |
| Profiles | `%LOCALAPPDATA%\Holix\profiles\<name>\` |
| Gateway log | `%LOCALAPPDATA%\Holix\profiles\<name>\gateway\` |

### Typical workflow

```powershell
holix models setup
holix tui
holix gateway start          # API + optional Telegram bot
holix -p shared telegram setup
```

Optional Windows extra for cleaner process cleanup: `pip install "Holix[windows]"`.

### Windows troubleshooting

| Symptom | Action |
|---------|--------|
| `holix` not found | New terminal; check `%USERPROFILE%\.local\bin` or re-run `.\scripts\install.ps1` |
| Script blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Unicode / TUI glitches | Use Windows Terminal; set UTF-8 in profile settings |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Developer install (from source)

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
uv run holix doctor
uv run holix tui
```

## First-time configuration

**Recommended** after curl install: bootstrap already configured LLM and Telegram. Otherwise:

```bash
holix bootstrap              # interactive: language, LLM, Telegram
# or step by step:
holix doctor
holix models setup
holix telegram setup
```

1. Copy environment defaults (optional): `cp .env.example .env` or use `~/.holix/global/.env`
2. Run diagnostics: `holix doctor`
3. Configure models (if skipped in bootstrap): `holix models setup`
4. Start chatting: `holix tui` or `holix chat-command`

UI language per profile: `/lang ru` or `/lang en` in TUI; stored in `profiles/<name>/data/locale.json`.

Data directory: `~/.holix/` (Linux/macOS), `%LOCALAPPDATA%\Holix\` (Windows), or `HOLIX_HOME`.  
Profile data: `profiles/<name>/` (not in the project directory). Logs: [LOGS.md](LOGS.md). See [CONFIGURATION.md](CONFIGURATION.md).

## Updates

```bash
holix update --channel pypi    # upgrade from PyPI (recommended for pipx installs)
holix update --check           # check only
holix update --channel git --repo /path/to/HolixAgent
holix update --force           # reinstall even if version matches
```

Or manually: `pipx upgrade Holix` / `pip install -U Holix`

## Docker

```bash
docker compose up -d
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for production layout, systemd, and CI.

## Uninstall

1. Remove the `holix` shim from your PATH directory (installer prints the path).
2. Optionally delete `~/.holix/` (profiles, gateway state, logs).
3. Remove the clone directory if you no longer need source.

## Troubleshooting install

| Symptom | Action |
|---------|--------|
| `holix: command not found` | Re-run `holix install` or add `~/.local/bin` to PATH |
| Python version error | Install Python 3.12+; `uv python install 3.12` |
| Import errors after pull | `holix update --force` or `uv sync && uv pip install -e .` |
| Doctor reports missing provider | `holix models setup` or `holix doctor --fix` |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).