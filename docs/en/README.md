# Holix Documentation (English)

Holix is a self-improving AI agent with memory, skills, tool calling, MCP, CLI, TUI, API gateway, and Telegram.

**Install from PyPI:** `pipx install Holix` — [pypi.org/project/Holix](https://pypi.org/project/Holix/)

> **Follow development:** subscribe to the [Telegram channel @holix_agent](https://t.me/holix_agent) for releases, roadmap, and project news.

## Getting started

1. [INSTALLATION.md](INSTALLATION.md) — PyPI install, **Windows**, extras, updates, Docker
2. [START_HERE.md](START_HERE.md) — first run checklist
3. [QUICKSTART.md](QUICKSTART.md) — minimal command list
4. [CONFIGURATION.md](CONFIGURATION.md) — `.env`, profiles, secrets
5. [PROFILES.md](PROFILES.md) — **isolated profiles, SOUL/USER identity, access keys, multi-user setup, workspace jail**

## Interfaces

- [CLI.md](CLI.md) — **complete `holix` command reference**
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — **all `/` commands** (TUI, Telegram, chat)
- [EXECUTION_MODES.md](EXECUTION_MODES.md) — **ReAct, Plan, Hybrid, Auto** — how modes work and prompt examples
- [TUI.md](TUI.md) — `holix tui`, web mode, copy, hub UI
- [HUB.md](HUB.md) — `holix hub`, catalogs, `skill_assignments`
- [GATEWAY.md](GATEWAY.md) — `holix gateway start|stop|status|reload`
- [LINK.md](LINK.md) — **Holix Link** — remote folder access behind NAT (`holix link`, `holix-link` client)
- [GATEWAY_API.md](GATEWAY_API.md) — **Complete API reference — every endpoint documented** (auth, `/api/holix/`, SaaS curl)
- [TELEGRAM.md](TELEGRAM.md) — Telegram
- [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md) — one bot / multiple bots, access requests, manual `map`
- [BROWSER_TOOLS.md](BROWSER_TOOLS.md) — Playwright `browser_*` tools

## Packaging

- [PYPI.md](PYPI.md) — build and publish to PyPI (`Holix`)

## Operations

- [LOGS.md](LOGS.md) — `holix logs`, rotation, debug mode
- [DOCTOR.md](DOCTOR.md) — `holix doctor` and `--fix`
- [SECURITY.md](SECURITY.md) — auth, tools, production checklist
- [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md) — terminal whitelist, blocked commands, confirmations
- [DEPLOYMENT.md](DEPLOYMENT.md) — Docker, systemd, CI
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — common failures

## Architecture

- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime, DI, events, graph

## Russian

[../ru/README.md](../ru/README.md)