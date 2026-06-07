# TUI

```bash
helix tui
helix tui -p myprofile

# Browser (textual-serve; one session per tab; token required)
uv sync --extra tui-web
helix tui --web
# Opens http://127.0.0.1:8787/?token=... (ephemeral token printed if omitted)

# LAN (full agent access — use a strong token)
helix tui --web --allow-lan --host 0.0.0.0 --port 8787 --token "$(openssl rand -hex 32)"
export HELIX_TUI_WEB_TOKEN="..."   # alternative to --token
```

Default: **code-style** UI (`cli/tui/code/`).

Legacy dashboard: `HELIX_TUI_LEGACY=1 helix tui`

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