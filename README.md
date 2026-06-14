# Holix — Self-Improving AI Agent

**Holix** is a self-improving AI agent with persistent memory, a skills system, tool calling, MCP integration, and multiple interfaces: CLI, TUI, API gateway, and Telegram.

[![PyPI](https://img.shields.io/pypi/v/Holix.svg)](https://pypi.org/project/Holix/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-en%20%7C%20ru-blue)](docs/README.md)

**Website:** [holix-agent.ru](https://holix-agent.ru) · **PyPI:** [Holix](https://pypi.org/project/Holix/) · **GitHub:** [javded-itres/Holix](https://github.com/javded-itres/Holix) · **Telegram:** [@holix_agent](https://t.me/holix_agent) · **Docs:** [EN](docs/en/README.md) · [RU](docs/ru/README.md) · **Donate:** [Boosty](https://boosty.to/javded/single-payment/donation/805721/target?share=target_link)

---

## Features

- **Tool calling** — files, shell, web, code execution, optional Playwright browser tools
- **Persistent memory** — SQLite conversations + ChromaDB semantic search
- **Skills** — markdown skills with auto-generation and hub catalogs (ClawHub, Hermes, Claude plugins)
- **MCP** — configure and assign Model Context Protocol servers per agent
- **Multi-provider** — Ollama, LiteLLM, OpenAI, Groq, and any OpenAI-compatible API
- **Interfaces** — `holix tui`, `holix chat-command`, `holix run`, `holix gateway`
- **Security** — API keys, rate limits, command whitelist, confirmation prompts
- **Operations** — `holix doctor`, `holix logs`, background gateway supervisor, Docker

---

## Quick start

### Install

**One-line install** (detects OS language, asks full vs minimal, runs `holix bootstrap` for LLM + Telegram):

```bash
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
```

Russian systems use Russian prompts automatically; English systems choose EN/RU. See [docs/en/INSTALLATION.md](docs/en/INSTALLATION.md).

**Install from PyPI** (Python 3.12+). Package: [`Holix`](https://pypi.org/project/Holix/), CLI command: `holix`:

```bash
pipx install Holix              # global CLI (recommended)
pipx install "Holix[all]"       # + telegram, browser, tui-web, voice

# or in a virtualenv:
pip install Holix
pip install "Holix[telegram,browser]"
```

Do not use `pip install helix` — that is a **different** package on PyPI.

Update later: `holix update --channel pypi`

**From source (developers):**

```bash
git clone https://github.com/javded-itres/Holix.git
cd Holix
./scripts/install.sh          # macOS / Linux
# Windows: .\scripts\install.ps1

holix version
holix doctor
```

Publishing: [docs/en/PYPI.md](docs/en/PYPI.md)

Developer install:

```bash
uv sync && uv pip install -e .
cp .env.example .env
```

Full guide: [docs/en/INSTALLATION.md](docs/en/INSTALLATION.md)

### Configure and run

```bash
holix models setup
holix tui                    # recommended UI
# or:
holix chat-command
holix run "What is in this repo?"
holix gateway start
```

---

## Documentation (English)

| Topic | Link |
|-------|------|
| Install & update | [INSTALLATION.md](docs/en/INSTALLATION.md) |
| **CLI reference** | [CLI.md](docs/en/CLI.md) |
| **Slash commands `/`** | [SLASH_COMMANDS.md](docs/en/SLASH_COMMANDS.md) |
| TUI | [TUI.md](docs/en/TUI.md) |
| Configuration | [CONFIGURATION.md](docs/en/CONFIGURATION.md) |
| Skill Hub | [HUB.md](docs/en/HUB.md) |
| API Gateway | [GATEWAY.md](docs/en/GATEWAY.md) |
| **MAX messenger** | [MAX.md](docs/en/MAX.md) |
| Logs | [LOGS.md](docs/en/LOGS.md) |
| Doctor | [DOCTOR.md](docs/en/DOCTOR.md) |
| Security | [SECURITY.md](docs/en/SECURITY.md) |
| Deployment | [DEPLOYMENT.md](docs/en/DEPLOYMENT.md) |
| Troubleshooting | [TROUBLESHOOTING.md](docs/en/TROUBLESHOOTING.md) |
| Architecture | [ARCHITECTURE.md](docs/en/ARCHITECTURE.md) |

## Документация (русский)

| Тема | Ссылка |
|------|--------|
| Установка | [INSTALLATION.md](docs/ru/INSTALLATION.md) |
| CLI | [CLI.md](docs/ru/CLI.md) |
| Слэш-команды | [SLASH_COMMANDS.md](docs/ru/SLASH_COMMANDS.md) |
| Начало | [START_HERE.md](docs/ru/START_HERE.md) |
| **MAX** | [MAX.md](docs/ru/MAX.md) |

---

## CLI at a glance

```bash
holix tui                          # main UI
holix run "query"                  # one-shot
holix models setup                 # providers
holix hub browse                   # external skills
holix mcp setup                    # MCP servers
holix gateway start|status|stop|reload
holix logs [-s agent] [-f]
holix doctor [--fix]
holix install | holix update
```

In TUI/Telegram, type `/help` for slash commands. See [docs/en/SLASH_COMMANDS.md](docs/en/SLASH_COMMANDS.md).

---

## Architecture

```
HolixAgent → run_agent_loop() (core/agent_execution.py)
           → LangGraph / AgentLoop
```

| Layer | Path |
|-------|------|
| Execution | `core/agent_execution.py` |
| Events | `core/agent_events.py` |
| Tools | `core/tools/` |
| Memory | `core/memory/` |
| CLI | `cli/main.py` |
| Gateway | `api/gateway.py` |

Details: [docs/en/ARCHITECTURE.md](docs/en/ARCHITECTURE.md)

---

## Docker

```bash
docker compose up -d
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Run tests before PRs: `uv run pytest -m "not llm"`.

---

## License

MIT — see [LICENSE](LICENSE)