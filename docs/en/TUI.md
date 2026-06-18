# TUI

```bash
holix tui
holix tui -p myprofile

# Browser (textual-serve; one session per tab; token required)
uv sync --extra tui-web
holix tui --web
# Opens http://127.0.0.1:8787/?token=... (ephemeral token printed if omitted)

# LAN (full agent access — use a strong token)
holix tui --web --allow-lan --host 0.0.0.0 --port 8787 --token "$(openssl rand -hex 32)"
export HOLIX_TUI_WEB_TOKEN="..."   # alternative to --token
```

Terminal UI: **code-style** interface (`cli/tui/code/`).

## Copy

- **Main chat:** select text → bottom **Copy** bar (no ⌃C/⌘C for last message)
- **Copy window (F2 / `/open`):** `⌃C` / `⌘C` / `Ctrl+Shift+C` copies selection or full transcript
- Slash: `/copy`, `/copy tool`, `/copy all` still work from chat

## Skill Hub

| Slash | Action |
|-------|--------|
| `/hub` | Pick catalog → browse & install |
| `/hub browse` | Open browser for current catalog |
| `/hub installed` | Installed hub skills, plugins, MCP |

See [HUB.md](HUB.md).

## Background processes

When the agent starts a long-running command (dev server, watch task), a **process bar** appears at the bottom of the chat.

| Action | How |
|--------|-----|
| View log | Click the process bar |
| List processes | `/process` or `/process list` |
| Stop process | `/process-stop` or click ⏹ on the bar |
| Stop agent only | `/stop` (does not kill background servers unless you use `/process-stop`) |

Process cwd follows `working_directory` → workspace jail → profile workspace. Venv is added to `PATH`; `PYTHONUNBUFFERED=1`.

## Cron from chat

Recurring natural-language requests (e.g. «send news every day at 10 am») auto-create gateway cron jobs in TUI — see [CRON.md](CRON.md). Manage with `/cron` or `holix cron list`.