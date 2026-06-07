# Installation

Helix targets **Python 3.14+** and is packaged as a Typer CLI (`helix`). Choose one of the paths below depending on whether you run from source or want a global command.

## Requirements

| Requirement | Notes |
|-------------|--------|
| Python | 3.14 or newer |
| [uv](https://github.com/astral-sh/uv) | Recommended for deps and `uv run` |
| LLM endpoint | OpenAI-compatible API (Ollama, LiteLLM, OpenAI, Groq, …) |

Optional extras (install when needed):

| Extra | Command | Enables |
|-------|---------|---------|
| `telegram` | `uv sync --extra telegram` | `helix telegram`, gateway Telegram companion |
| `browser` | `uv sync --extra browser` + `playwright install chromium` | Playwright `browser_*` tools — see [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |
| `tui-web` | `uv sync --extra tui-web` | `helix tui --web` (browser-hosted TUI) |
| `windows` | `uv sync --extra windows` | `psutil` for process-tree cleanup (optional on Windows) |
| `all` | `uv sync --extra all` | telegram + browser + tui-web + windows |

## Quick install (recommended for users)

### From PyPI

PyPI package name is **`helix-agent`** (not `helix` — that name is used by another project).  
After install, the CLI command is **`helix`** in the environment’s `bin` directory.

**Global CLI from any folder** (recommended — no manual PATH):

```bash
pipx install helix-agent
# or:
uv tool install helix-agent

helix version
```

**Inside a virtualenv** (activate the venv, then `helix` works in any directory):

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install helix-agent
pip install "helix-agent[telegram,browser,tui-web]"
helix version
helix doctor
```

**User install without pipx** (`~/.local/bin` must be on your PATH):

```bash
pip install --user helix-agent
# macOS/Linux: ensure ~/.local/bin is in PATH, e.g. in ~/.zshrc:
#   export PATH="$HOME/.local/bin:$PATH"
helix version
```

See [PYPI.md](PYPI.md).

### From git

```bash
git clone https://github.com/YOUR_ORG/helix.git
cd helix
./scripts/install.sh
# Windows: .\scripts\install.ps1
```

Or after you already have `helix` on PATH:

```bash
helix install
helix install --extra telegram
helix install --extra browser
helix install --system          # all users; may need sudo / Administrator
```

The installer:

- Detects the repo root and runs `uv sync` (with selected extras)
- Installs the package editable (`uv pip install -e .`)
- Adds `~/.local/bin` (or system path) to your shell PATH unless `--no-path`

Verify:

```bash
helix version
helix doctor
```

## Developer install (from source)

```bash
git clone https://github.com/YOUR_ORG/helix.git
cd helix
uv sync
uv pip install -e .
cp .env.example .env
helix doctor
helix models setup
```

Run without global install:

```bash
uv run helix doctor
uv run helix tui
```

## First-time configuration

1. Copy environment defaults: `cp .env.example .env`
2. Run diagnostics: `helix doctor`
3. Configure models: `helix models setup`
4. Start chatting: `helix tui` or `helix chat-command`

Data directory: `~/.helix/` (Linux/macOS), `%LOCALAPPDATA%\Helix\` (Windows), or `HELIX_HOME`.  
Profile data: `profiles/<name>/` (not in the project directory). Logs: [LOGS.md](LOGS.md). See [CONFIGURATION.md](CONFIGURATION.md).

## Updates

```bash
helix update              # auto: git pull + reinstall, or PyPI when published
helix update --check      # check only
helix update --channel git --repo /path/to/helix
helix update --force      # reinstall even if version matches
```

## Docker

```bash
docker compose up -d
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for production layout, systemd, and CI.

## Uninstall

1. Remove the `helix` shim from your PATH directory (installer prints the path).
2. Optionally delete `~/.helix/` (profiles, gateway state, logs).
3. Remove the clone directory if you no longer need source.

## Troubleshooting install

| Symptom | Action |
|---------|--------|
| `helix: command not found` | Re-run `helix install` or add `~/.local/bin` to PATH |
| Python version error | Install Python 3.14+; `uv python install 3.14` |
| Import errors after pull | `helix update --force` or `uv sync && uv pip install -e .` |
| Doctor reports missing provider | `helix models setup` or `helix doctor --fix` |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).