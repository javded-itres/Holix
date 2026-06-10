# Helix Documentation (English)

Helix is a self-improving AI agent with memory, skills, tool calling, MCP, CLI, TUI, API gateway, and Telegram.

**Install from PyPI:** `pipx install HelixAgentAi` — [pypi.org/project/HelixAgentAi](https://pypi.org/project/HelixAgentAi/)

> **Follow development:** subscribe to the [Telegram channel @helix_agent](https://t.me/helix_agent) for releases, roadmap, and project news.

## Getting started

1. [INSTALLATION.md](INSTALLATION.md) — PyPI install, **Windows**, extras, updates, Docker
2. [START_HERE.md](START_HERE.md) — first run checklist
3. [QUICKSTART.md](QUICKSTART.md) — minimal command list
4. [CONFIGURATION.md](CONFIGURATION.md) — `.env`, profiles, secrets
5. [PROFILES.md](PROFILES.md) — **isolated profiles, access keys, multi-user setup, workspace jail**

## Interfaces

- [CLI.md](CLI.md) — **complete `helix` command reference**
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — **all `/` commands** (TUI, Telegram, chat)
- [EXECUTION_MODES.md](EXECUTION_MODES.md) — **ReAct, Plan, Hybrid, Auto** — how modes work and prompt examples
- [TUI.md](TUI.md) — `helix tui`, web mode, copy, hub UI
- [HUB.md](HUB.md) — `helix hub`, catalogs, `skill_assignments`
- [GATEWAY.md](GATEWAY.md) — `helix gateway start|stop|status|reload`
- [TELEGRAM.md](TELEGRAM.md) — Telegram
- [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md) — one bot / multiple bots, user id mapping bot
- [BROWSER_TOOLS.md](BROWSER_TOOLS.md) — Playwright `browser_*` tools

## Packaging

- [PYPI.md](PYPI.md) — build and publish to PyPI (`HelixAgentAi`)

## Operations

- [LOGS.md](LOGS.md) — `helix logs`, rotation, debug mode
- [DOCTOR.md](DOCTOR.md) — `helix doctor` and `--fix`
- [SECURITY.md](SECURITY.md) — auth, tools, production checklist
- [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md) — terminal whitelist, blocked commands, confirmations
- [DEPLOYMENT.md](DEPLOYMENT.md) — Docker, systemd, CI
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — common failures

## Architecture

- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime, DI, events, graph

## Russian

[../ru/README.md](../ru/README.md)