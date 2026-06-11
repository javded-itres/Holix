# Start Here

Follow this checklist for a working Holix install on a new machine.

## Requirements

- Python **3.12+**
- An OpenAI-compatible LLM ([Ollama](https://ollama.com), LiteLLM, OpenAI, Groq, …)
- [pipx](https://pipx.pypa.io/) (recommended) or `pip` in a venv

## 1. Install from PyPI

Package **[HolixAgentAi](https://pypi.org/project/HelixAgentAi/)** on PyPI; terminal command **`holix`**.

```bash
pipx install HelixAgentAi
# optional extras (Telegram, browser, web TUI, voice):
pipx install "HelixAgentAi[all]"

holix version
holix doctor
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
mkdir -p ~/.holix
# On first run Holix may seed ~/.holix/.env; or copy from the repo:
# cp .env.example ~/.holix/.env
holix doctor
holix doctor --fix    # optional: repair config.yaml
```

On the **first conversation** in a new profile, Holix runs a short onboarding (while `INIT.md` exists): introduce yourself, set agent personality (`SOUL.md`), and save your preferences (`USER.md`). See [PROFILES.md](PROFILES.md#agent-identity-soul-init-user).

## 3. Configure models

```bash
holix models setup
holix models list
holix config show
```

## 4. Choose an interface

| Interface | Command | Best for |
|-----------|---------|----------|
| TUI (recommended) | `holix tui` | Daily use, tools, hub, MCP |
| Terminal chat | `holix chat-command` | Lightweight REPL |
| One-shot | `holix run "…"` | Scripts, automation |
| HTTP API | `holix gateway start` | Apps, OpenAI-compatible clients |

In TUI or Telegram, type **`/help`** for slash commands: [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

## 5. Optional features

```bash
pipx install "HelixAgentAi[telegram]"   # or reinstall with [all]
holix -p shared telegram setup
# multi-user: users send /start, then holix -p shared telegram requests approve …
pipx install "HelixAgentAi[browser]"
playwright install chromium            # after browser extra
pipx install "HelixAgentAi[tui-web]"   # holix tui --web
holix hub browse
holix mcp setup
```

## Production

```bash
export HOLIX_ENV=production
export HOLIX_REQUIRE_AUTH=true
export HOLIX_API_KEY_PEPPER=$(openssl rand -hex 32)
holix gateway start
```

Read [SECURITY.md](SECURITY.md) and [DEPLOYMENT.md](DEPLOYMENT.md).

## Next steps

- Full CLI: [CLI.md](CLI.md)
- Config reference: [CONFIGURATION.md](CONFIGURATION.md)
- Logs: `holix logs` — [LOGS.md](LOGS.md)
- Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)