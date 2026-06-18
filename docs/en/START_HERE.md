# Start Here

Checklist after [INSTALLATION.md](INSTALLATION.md). Assumes `holix` is on your PATH (Path A) or Docker is running (Path B).

## 1. Verify install

```bash
holix version
holix doctor
holix doctor --fix    # optional: repair config.yaml
```

Docker:

```bash
docker compose ps
docker compose exec holix holix doctor
```

## 2. First-time config

On the **first conversation** in a new profile, Holix runs short onboarding (`INIT.md`): introduce yourself, set agent personality (`SOUL.md`), save preferences (`USER.md`). See [PROFILES.md](PROFILES.md#agent-identity-soul-init-user).

If bootstrap did not run:

```bash
holix bootstrap
holix models setup
holix models list
holix config show
```

## 3. Choose an interface

| Interface | Command | Best for |
|-----------|---------|----------|
| TUI (recommended) | `holix tui` | Daily use, tools, hub, MCP |
| Terminal chat | `holix chat-command` | Lightweight REPL |
| One-shot | `holix run "…"` | Scripts, automation |
| HTTP API | `holix gateway start` | Apps, OpenAI-compatible clients |
| Telegram | `holix -p shared telegram setup` then gateway | Mobile access — [TELEGRAM.md](TELEGRAM.md) |
| MAX | `holix max setup` | MAX messenger — [MAX.md](MAX.md) |

Slash commands in TUI/Telegram: **`/help`** — [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

## 4. Optional features

Install extras only when needed — see [INSTALLATION.md](INSTALLATION.md#optional-extras-path-a):

```bash
uv tool install "Holix[all]"    # or pipx reinstall
holix -p shared telegram setup
holix hub browse
holix mcp setup
playwright install chromium     # after [browser] extra
```

## 5. Production

```bash
export HOLIX_ENV=production
export HOLIX_REQUIRE_AUTH=true
export HOLIX_API_KEY_PEPPER=$(openssl rand -hex 32)
holix gateway start
```

Read [SECURITY.md](SECURITY.md) and [DEPLOYMENT.md](DEPLOYMENT.md).

## Command cheat sheet

Quick reference (details in linked docs):

```bash
holix doctor
holix models setup
holix run "Hello"
holix tui                       # /help for slash commands
holix gateway start
holix gateway status
holix cron list                 # needs running gateway
holix launch setup              # external CLIs in tmux (Linux/macOS)
holix logs -l error
holix hub browse
holix mcp setup
holix update --channel pypi
```

Repair: `holix doctor --fix`

## Next steps

| Topic | Doc |
|-------|-----|
| Configuration | [CONFIGURATION.md](CONFIGURATION.md) |
| Profiles & isolation | [PROFILES.md](PROFILES.md) |
| Full CLI reference | [CLI.md](CLI.md) |
| Scheduled tasks | [CRON.md](CRON.md) |
| Logs | [LOGS.md](LOGS.md) |
| Problems | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Learning path (all topics) | [USER_GUIDE.md](USER_GUIDE.md) |