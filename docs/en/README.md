# Holix Documentation (English)

Holix is a self-improving AI agent: memory, skills, MCP, CLI, TUI, API gateway, Telegram, and MAX.

**Install:** `uv tool install Holix` or see [INSTALLATION.md](INSTALLATION.md) (local **uv** path vs **Docker**).

> **Follow development:** [Telegram @helix_agent](https://t.me/helix_agent)

---

## Start here

| Step | Document |
|------|----------|
| 1. Install | [INSTALLATION.md](INSTALLATION.md) |
| 2. First run checklist | [START_HERE.md](START_HERE.md) |
| 3. Full learning path | [USER_GUIDE.md](USER_GUIDE.md) |

---

## Documentation map

### Install & configure

- [INSTALLATION.md](INSTALLATION.md) — Path A: uv / pipx · Path B: Docker
- [START_HERE.md](START_HERE.md) — checklist + command cheat sheet
- [CONFIGURATION.md](CONFIGURATION.md) — `.env`, YAML layers
- [MODELS.md](MODELS.md) — providers, `agent_models`, fallbacks
- [PROFILES.md](PROFILES.md) — isolation, SOUL/USER, jail, keys
- [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md) — at-rest encryption

### Using Holix

- [TUI.md](TUI.md) · [SLASH_COMMANDS.md](SLASH_COMMANDS.md) · [EXECUTION_MODES.md](EXECUTION_MODES.md)
- [CLI.md](CLI.md) — complete command reference
- [HUB.md](HUB.md) · [BROWSER_TOOLS.md](BROWSER_TOOLS.md)
- [MCP.md](MCP.md) · [MEMORY.md](MEMORY.md)

### Agents & automation

- [EXECUTION_MODES.md](EXECUTION_MODES.md) — ReAct / Plan / Hybrid, **Reflexion**, step budget
- [SUBAGENTS.md](SUBAGENTS.md) — workers, **supervisor**, rework · [A2A.md](A2A.md) — Agent2Agent protocol · [LAUNCH.md](LAUNCH.md) · [CRON.md](CRON.md)
- [SUBAGENT_SUPERVISOR.md](SUBAGENT_SUPERVISOR.md) — design notes

### Integrations & API

- [TELEGRAM.md](TELEGRAM.md) · [MAX.md](MAX.md)
- [GATEWAY.md](GATEWAY.md) · [GATEWAY_API.md](GATEWAY_API.md)

### Extensions ecosystem

- [holix-sdk](https://github.com/javded-itres/holix-sdk) — separate package (PyPI: `holix-sdk`)
- [EXTENSIONS.md](EXTENSIONS.md) — create extensions (step-by-step, mirrored in holix-sdk repo)
- [BUILD_WITHOUT_HOLIX.md](BUILD_WITHOUT_HOLIX.md) · [EXTENSION_GATEWAY.md](EXTENSION_GATEWAY.md)

### Security & operations

- [SECURITY.md](SECURITY.md) · [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md)
- [DEPLOYMENT.md](DEPLOYMENT.md) · [LOGS.md](LOGS.md) · [DOCTOR.md](DOCTOR.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

### Internals

- [ARCHITECTURE.md](ARCHITECTURE.md) · [CHANGELOG.md](../CHANGELOG.md) · [PYPI.md](PYPI.md)

---

## Russian

[../ru/README.md](../ru/README.md)

**Website:** [holix-agent.ru/docs](https://holix-agent.ru/docs)