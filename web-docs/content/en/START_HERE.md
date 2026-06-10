# Start Here

Follow this checklist for a working Helix install on a new machine.

## Requirements

- Python **3.12+**
- An OpenAI-compatible LLM ([Ollama](https://ollama.com), LiteLLM, OpenAI, Groq, …)
- [pipx](https://pipx.pypa.io/) (recommended) or `pip` in a venv

## 1. Install from PyPI

Package **[HelixAgentAi](https://pypi.org/project/HelixAgentAi/)** on PyPI; terminal command **`helix`**.

```bash
pipx install HelixAgentAi
# optional extras (Telegram, browser, web TUI, voice):
pipx install "HelixAgentAi[all]"

helix version
helix doctor
```

Inside a virtualenv instead of pipx:

```bash
python -m venv .venv && source .venv/bin/activate
pip install HelixAgentAi
```

Do not run `pip install helix` — that installs an unrelated package.

**Developers** (from git): [INSTALLATION.md](INSTALLATION.md#developer-install-from-source)

## 2. First-time config

```bash
mkdir -p ~/.helix
# On first run Helix may seed ~/.helix/.env; or copy from the repo:
# cp .env.example ~/.helix/.env
helix doctor
helix doctor --fix    # optional: repair config.yaml
```

## 3. Configure models

```bash
helix models setup
helix models list
helix config show
```

## 4. Choose an interface

| Interface | Command | Best for |
|-----------|---------|----------|
| TUI (recommended) | `helix tui` | Daily use, tools, hub, MCP |
| Terminal chat | `helix chat-command` | Lightweight REPL |
| One-shot | `helix run "…"` | Scripts, automation |
| HTTP API | `helix gateway start` | Apps, OpenAI-compatible clients |

In TUI or Telegram, type **`/help`** for slash commands: [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

## 5. Optional features

```bash
pipx install "HelixAgentAi[telegram]"   # or reinstall with [all]
helix -p shared telegram setup
# multi-user: users send /start, then helix -p shared telegram requests approve …
pipx install "HelixAgentAi[browser]"
playwright install chromium            # after browser extra
pipx install "HelixAgentAi[tui-web]"   # helix tui --web
helix hub browse
helix mcp setup
```

## Production

```bash
export HELIX_ENV=production
export HELIX_REQUIRE_AUTH=true
export HELIX_API_KEY_PEPPER=$(openssl rand -hex 32)
helix gateway start
```

Read [SECURITY.md](SECURITY.md) and [DEPLOYMENT.md](DEPLOYMENT.md).

## Next steps

- Full CLI: [CLI.md](CLI.md)
- Config reference: [CONFIGURATION.md](CONFIGURATION.md)
- Logs: `helix logs` — [LOGS.md](LOGS.md)
- Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)