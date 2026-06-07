# Quickstart

```bash
./scripts/install.sh   # or: uv sync && uv pip install -e .
cp .env.example .env
helix doctor
helix models setup
helix run "Hello"
helix tui              # primary UI; /help for slash commands
helix gateway start
helix gateway status
helix logs -l error          # inspect failures
```

Repair config:

```bash
helix doctor --fix
```

Optional:

```bash
uv sync --extra telegram
export TELEGRAM_BOT_TOKEN=...
helix gateway start
helix hub browse
helix mcp setup
```

See [CLI.md](CLI.md) and [SLASH_COMMANDS.md](SLASH_COMMANDS.md).