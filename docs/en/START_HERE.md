# Start Here

Follow this checklist for a working Holix install on a new machine.

## Requirements

- Python **3.12+**
- An OpenAI-compatible LLM ([Ollama](https://ollama.com), LiteLLM, OpenAI, Groq, …)
- [pipx](https://pipx.pypa.io/) (recommended) or `pip` in a venv

## 1. Install

**Fastest (macOS/Linux):** one-line installer with language detection, full/minimal choice, and `holix bootstrap`:

```bash
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
```

See [INSTALLATION.md](INSTALLATION.md#one-line-install-curl) for language rules and bootstrap details.

**Manual PyPI:** package **[Holix](https://pypi.org/project/Holix/)**; terminal command **`holix`**.

```bash
pipx install Holix
# optional extras (Telegram, browser, web TUI, voice):
pipx install "Holix[all]"

holix bootstrap    # LLM + optional Telegram; sets profile locale
holix version
holix doctor
```

Inside a virtualenv instead of pipx:

```bash
python -m venv .venv && source .venv/bin/activate
pip install Holix
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
pipx install "Holix[telegram]"   # or reinstall with [all]
holix -p shared telegram setup
# multi-user: users send /start, then holix -p shared telegram requests approve …
pipx install "Holix[max]"
holix -p shared max setup
# MAX in production: holix -p shared gateway start (webhook) — see MAX.md
pipx install "Holix[browser]"
playwright install chromium            # after browser extra
pipx install "Holix[tui-web]"   # holix tui --web
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

- [MAX.md](MAX.md) — MAX messenger bot
- Full CLI: [CLI.md](CLI.md)
- Config reference: [CONFIGURATION.md](CONFIGURATION.md)
- Logs: `holix logs` — [LOGS.md](LOGS.md)
- Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)