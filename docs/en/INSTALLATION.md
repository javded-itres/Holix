# Installation

Helix targets **Python 3.12+** and is packaged as a Typer CLI (`helix`). Choose one of the paths below depending on whether you run from source or want a global command.

## Requirements

| Requirement | Notes |
|-------------|--------|
| Python | 3.12 or newer |
| [uv](https://github.com/astral-sh/uv) | Recommended for deps and `uv run` |
| LLM endpoint | OpenAI-compatible API (Ollama, LiteLLM, OpenAI, Groq, …) |

Optional extras (install when needed):

| Extra | PyPI (`pip` / `pipx`) | From source (`uv sync`) | Enables |
|-------|----------------------|-------------------------|---------|
| `telegram` | `pip install "HelixAgentAi[telegram]"` | `uv sync --extra telegram` | `helix telegram`, gateway Telegram |
| `browser` | `pip install "HelixAgentAi[browser]"` | `uv sync --extra browser` | Playwright tools — [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |
| `voice` | `pip install "HelixAgentAi[voice]"` | `uv sync --extra voice` | Whisper voice notes in Telegram |
| `tui-web` | `pip install "HelixAgentAi[tui-web]"` | `uv sync --extra tui-web` | `helix tui --web` |
| `windows` | `pip install "HelixAgentAi[windows]"` | `uv sync --extra windows` | `psutil` process-tree cleanup |
| `all` | `pip install "HelixAgentAi[all]"` | `uv sync --extra all` | all of the above |

After the `browser` extra: `playwright install chromium`

## Quick install (recommended for users)

### From PyPI (recommended)

Published on [pypi.org/project/HelixAgentAi](https://pypi.org/project/HelixAgentAi/) (current: **0.1.8**).

Package name **`HelixAgentAi`** (not `helix` — that name is used by another project).  
After install, the CLI command is **`helix`** in the environment’s `bin` directory.

**Global CLI from any folder** (recommended — no manual PATH):

```bash
pipx install HelixAgentAi
# or:
uv tool install HelixAgentAi

helix version
```

**Inside a virtualenv** (activate the venv, then `helix` works in any directory):

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install HelixAgentAi
pip install "HelixAgentAi[telegram,browser,tui-web]"
helix version
helix doctor
```

**User install without pipx** (`~/.local/bin` must be on your PATH):

```bash
pip install --user HelixAgentAi
# macOS/Linux: ensure ~/.local/bin is in PATH, e.g. in ~/.zshrc:
#   export PATH="$HOME/.local/bin:$PATH"
helix version
```

See [PYPI.md](PYPI.md).

### From git

```bash
git clone https://github.com/javded-itres/HelixAgent.git
cd HelixAgent
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

## Windows

**Requirements:** Python 3.12+ from [python.org](https://www.python.org/downloads/) (check “Add python.exe to PATH” during setup).  
**Recommended:** [uv](https://github.com/astral-sh/uv) for dependencies.

### Global `helix` from any folder

**PyPI (simplest):**

```powershell
pipx install HelixAgentAi
# or:
uv tool install HelixAgentAi

helix version
helix doctor
```

**From git clone:**

```powershell
git clone https://github.com/javded-itres/HelixAgent.git
cd HelixAgent
.\scripts\install.ps1
# or, if helix is already on PATH:
helix install --extra telegram
```

The installer adds Helix to your user PATH. **Open a new PowerShell window** after install, then run `helix version`.

### Data and profiles

| Item | Path |
|------|------|
| Helix home | `%LOCALAPPDATA%\Helix\` (or `HELIX_HOME`) |
| Profiles | `%LOCALAPPDATA%\Helix\profiles\<name>\` |
| Gateway log | `%LOCALAPPDATA%\Helix\profiles\<name>\gateway\` |

### Typical workflow

```powershell
helix models setup
helix tui
helix gateway start          # API + optional Telegram bot
helix -p shared telegram setup
```

Optional Windows extra for cleaner process cleanup: `pip install "HelixAgentAi[windows]"`.

### Windows troubleshooting

| Symptom | Action |
|---------|--------|
| `helix` not found | New terminal; check `%USERPROFILE%\.local\bin` or re-run `.\scripts\install.ps1` |
| Script blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Unicode / TUI glitches | Use Windows Terminal; set UTF-8 in profile settings |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Developer install (from source)

```bash
git clone https://github.com/javded-itres/HelixAgent.git
cd HelixAgent
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
helix update --channel pypi    # upgrade from PyPI (recommended for pipx installs)
helix update --check           # check only
helix update --channel git --repo /path/to/HelixAgent
helix update --force           # reinstall even if version matches
```

Or manually: `pipx upgrade HelixAgentAi` / `pip install -U HelixAgentAi`

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
| Python version error | Install Python 3.12+; `uv python install 3.12` |
| Import errors after pull | `helix update --force` or `uv sync && uv pip install -e .` |
| Doctor reports missing provider | `helix models setup` or `helix doctor --fix` |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).