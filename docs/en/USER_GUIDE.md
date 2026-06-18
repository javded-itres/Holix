# Holix — Learning Path

Curated route through the documentation. Each topic has **one canonical page** — follow links instead of duplicating content here.

> Package **`Holix`** on PyPI; CLI command **`holix`**.  
> Not in the website sidebar — use this page from [README](README.md) or [START_HERE](START_HERE.md).

---

## 1. Install and first run

| Step | Doc |
|------|-----|
| Choose local (uv) or Docker | [INSTALLATION.md](INSTALLATION.md) |
| Checklist after install | [START_HERE.md](START_HERE.md) |
| Command cheat sheet | [START_HERE.md § Cheat sheet](START_HERE.md#command-cheat-sheet) |
| Diagnostics | [DOCTOR.md](DOCTOR.md) |

---

## 2. Configuration and profiles

| Topic | Doc |
|-------|-----|
| `.env`, YAML layers, models overview | [CONFIGURATION.md](CONFIGURATION.md) |
| Isolated profiles, SOUL/USER, jail, keys | [PROFILES.md](PROFILES.md) |
| Encryption at rest | [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md) |
| Execution modes (ReAct, Plan, Hybrid) | [EXECUTION_MODES.md](EXECUTION_MODES.md) |

---

## 3. Daily interfaces

| Interface | Doc |
|-----------|-----|
| TUI (recommended) | [TUI.md](TUI.md) |
| Slash commands `/` | [SLASH_COMMANDS.md](SLASH_COMMANDS.md) |
| Full CLI reference | [CLI.md](CLI.md) |
| Skill Hub | [HUB.md](HUB.md) |
| MCP servers | [CONFIGURATION.md](CONFIGURATION.md) + `holix mcp` in [CLI.md](CLI.md) |

---

## 4. Agents and automation

| Topic | Doc |
|-------|-----|
| Sub-agents | [SUBAGENTS.md](SUBAGENTS.md) |
| External CLIs (`holix launch`) | [LAUNCH.md](LAUNCH.md) |
| Scheduled tasks (cron) | [CRON.md](CRON.md) |
| Browser tools | [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |

---

## 5. Integrations

| Channel | Doc |
|---------|-----|
| Telegram | [TELEGRAM.md](TELEGRAM.md) |
| MAX messenger | [MAX.md](MAX.md) |
| API gateway | [GATEWAY.md](GATEWAY.md) |
| HTTP API reference | [GATEWAY_API.md](GATEWAY_API.md) |

---

## 6. Security and operations

| Topic | Doc |
|-------|-----|
| Production checklist | [SECURITY.md](SECURITY.md) |
| Terminal whitelist & confirmations | [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md) |
| Docker / systemd / TLS | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Logs | [LOGS.md](LOGS.md) |
| Troubleshooting | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |

---

## 7. Internals

| Topic | Doc |
|-------|-----|
| Architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Changelog | [../CHANGELOG.md](../CHANGELOG.md) |
| PyPI publishing | [PYPI.md](PYPI.md) |

---

## Suggested order for new users

1. [INSTALLATION.md](INSTALLATION.md) → [START_HERE.md](START_HERE.md)  
2. [CONFIGURATION.md](CONFIGURATION.md) → [PROFILES.md](PROFILES.md)  
3. [TUI.md](TUI.md) + [SLASH_COMMANDS.md](SLASH_COMMANDS.md)  
4. [GATEWAY.md](GATEWAY.md) or [TELEGRAM.md](TELEGRAM.md) / [MAX.md](MAX.md) as needed  
5. [SECURITY.md](SECURITY.md) before production