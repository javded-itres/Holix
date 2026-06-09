# Helix — Self-Improving AI Agent

**Helix** is a self-improving AI agent with persistent memory, a skills system, tool calling, MCP integration, and multiple interfaces: CLI, TUI, API gateway, and Telegram.

[![PyPI](https://img.shields.io/pypi/v/HelixAgentAi.svg)](https://pypi.org/project/HelixAgentAi/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-en%20%7C%20ru-blue)](docs/README.md)

**Website:** [helix-agent.ru](https://helix-agent.ru) · **PyPI:** [HelixAgentAi](https://pypi.org/project/HelixAgentAi/) · **GitHub:** [javded-itres/HelixAgent](https://github.com/javded-itres/HelixAgent) · **Telegram:** [@helix_agent](https://t.me/helix_agent) · **Docs:** [EN](docs/en/README.md) · [RU](docs/ru/README.md) · **Donate:** [Boosty](https://boosty.to/javded/single-payment/donation/805721/target?share=target_link)

---

## Features

- **Tool calling** — files, shell, web, code execution, optional Playwright browser tools
- **Persistent memory** — SQLite conversations + ChromaDB semantic search
- **Skills** — markdown skills with auto-generation and hub catalogs (ClawHub, Hermes, Claude plugins)
- **MCP** — configure and assign Model Context Protocol servers per agent
- **Multi-provider** — Ollama, LiteLLM, OpenAI, Groq, and any OpenAI-compatible API
- **Interfaces** — `helix tui`, `helix chat-command`, `helix run`, `helix gateway`
- **Security** — API keys, rate limits, command whitelist, confirmation prompts
- **Operations** — `helix doctor`, `helix logs`, background gateway supervisor, Docker

---

## Quick start

### Install

**Install from PyPI** (Python 3.12+). Package: [`HelixAgentAi`](https://pypi.org/project/HelixAgentAi/), CLI command: `helix`:

```bash
pipx install HelixAgentAi              # global CLI (recommended)
pipx install "HelixAgentAi[all]"       # + telegram, browser, tui-web, voice

# or in a virtualenv:
pip install HelixAgentAi
pip install "HelixAgentAi[telegram,browser]"
```

Do not use `pip install helix` — that is a **different** package on PyPI.

Update later: `helix update --channel pypi`

**From source (developers):**

```bash
git clone https://github.com/javded-itres/HelixAgent.git
cd HelixAgent
./scripts/install.sh          # macOS / Linux
# Windows: .\scripts\install.ps1

helix version
helix doctor
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
helix models setup
helix tui                    # recommended UI
# or:
helix chat-command
helix run "What is in this repo?"
helix gateway start
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

---

## CLI at a glance

```bash
helix tui                          # main UI
helix run "query"                  # one-shot
helix models setup                 # providers
helix hub browse                   # external skills
helix mcp setup                    # MCP servers
helix gateway start|status|stop|reload
helix logs [-s agent] [-f]
helix doctor [--fix]
helix install | helix update
```

In TUI/Telegram, type `/help` for slash commands. See [docs/en/SLASH_COMMANDS.md](docs/en/SLASH_COMMANDS.md).

---

## Architecture

```
HelixAgent → run_agent_loop() (core/agent_execution.py)
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