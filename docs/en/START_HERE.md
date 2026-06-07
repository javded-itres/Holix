# Start Here

Follow this checklist for a working Helix install on a new machine.

## Requirements

- Python **3.14+**
- [uv](https://github.com/astral-sh/uv) (recommended)
- An OpenAI-compatible LLM ([Ollama](https://ollama.com), LiteLLM, OpenAI, Groq, …)

## 1. Install

```bash
git clone https://github.com/YOUR_ORG/helix.git
cd helix
./scripts/install.sh
# or: uv sync && uv pip install -e .
cp .env.example .env
```

Details: [INSTALLATION.md](INSTALLATION.md)

## 2. Diagnose

```bash
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
uv sync --extra telegram    # helix telegram setup
uv sync --extra browser     # Playwright tools — BROWSER_TOOLS.md
uv sync --extra tui-web     # helix tui --web
helix hub browse            # external skills
helix mcp setup             # MCP servers
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