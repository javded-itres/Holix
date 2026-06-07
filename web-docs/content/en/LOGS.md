# Logs and observability

Helix writes structured logs under the data directory. Use **`helix logs`** to view, filter, rotate, and toggle debug mode.

## Data directory

| OS | Default path |
|----|----------------|
| Linux / macOS | `~/.helix/` |
| Windows | `%LOCALAPPDATA%\Helix\` |
| Override | `HELIX_HOME=/path/to/data` |
| Linux (XDG) | `$XDG_DATA_HOME/helix/` if `HELIX_HOME` unset |

Logs live in `{HELIX_HOME}/logs/` unless noted.

## Log files

| File | Source | Content |
|------|--------|---------|
| `logs/agent.jsonl` | Main agent | Tool calls, errors, final responses, skills, context events (JSON lines) |
| `logs/agent.debug.jsonl` | Agent (debug) | Same events when debug mode is on |
| `logs/subagent.jsonl` | Sub-agents | Spawn, terminate, task preview |
| `logs/helix.log` | System | Python root logger (rotating) |
| `gateway/gateway.log` | Gateway | Uvicorn / API supervisor |
| `profiles/<p>/data/cron/runs.log` | Cron | Scheduled job run lines |
| `logs/hub-autoupdate.log` | Hub | Optional autoupdate output |
| `logs/history_<profile>.txt` | Chat REPL | prompt_toolkit input history (not agent output) |

Agent and sub-agent **results** appear in `agent.jsonl` (`FinalResponseEvent`, tool results) and in conversation memory; cron summaries may also post to the bound TUI/Telegram session.

## `helix logs` commands

```bash
helix logs                          # last 80 lines, all sources
helix logs show -n 200              # more lines
helix logs -s agent                 # agent JSONL only
helix logs -s gateway               # gateway.log
helix logs -s cron -p work        # cron runs for profile
helix logs -s subagent              # sub-agent events
helix logs -s system                # helix.log
helix logs -l error                 # ERROR and above
helix logs -l warning               # WARNING and above
helix logs -g "Tool call"           # text filter
helix logs -f                       # follow (stream new lines)
helix logs --debug -v               # include debug file + extra fields
helix logs list                     # files and sizes
helix logs rotate                   # rotate oversized logs + purge old backups
helix logs debug on                 # enable debug (persisted)
helix logs debug off
helix logs debug status
```

### Source filter (`-s` / `--source`)

| Value | Files |
|-------|--------|
| `all` | All existing log files (default) |
| `agent` | `agent.jsonl`, `agent.debug.jsonl` |
| `gateway` | `gateway/gateway.log` |
| `cron` | `profiles/<profile>/data/cron/runs.log` |
| `subagent` | `subagent.jsonl` |
| `system` | `helix.log`, `hub-autoupdate.log` |

## Debug mode

Debug is **off** by default. When enabled:

- Extra detail is written to `logs/agent.debug.jsonl`
- Sub-agent debug lines are duplicated there
- Root log level becomes `DEBUG`
- State is stored in `logs/logging.json` (survives restarts)

```bash
helix logs debug on
# or in .env:
# HELIX_LOG_DEBUG=true
```

CLI debug toggle and `.env` are combined: either can enable debug.

## Rotation and retention

Configured via environment (see [CONFIGURATION.md](CONFIGURATION.md#logging)):

| Variable | Default | Meaning |
|----------|---------|---------|
| `HELIX_LOG_MAX_BYTES` | `10485760` (10 MiB) | Rotate when file exceeds size |
| `HELIX_LOG_BACKUP_COUNT` | `10` | Keep N rotated backups (`.1`, `.2`, …) |
| `HELIX_LOG_ROTATION_DAYS` | `14` | Delete backups older than N days (`helix logs rotate --purge`) |

Manual rotation:

```bash
helix logs rotate
helix logs rotate --no-purge   # rotate only, keep old backups
```

`helix.log` and `subagent.jsonl` use Python `RotatingFileHandler` automatically. `helix logs rotate` handles other files by size.

## JSONL event shape (agent)

Each line in `agent.jsonl` is JSON, for example:

```json
{
  "timestamp": "2026-06-06T12:00:00+00:00",
  "level": "INFO",
  "category": "agent",
  "message": "Tool call completed: read_file",
  "tool": "read_file",
  "conversation_id": "tui_default",
  "event_type": "tool_call_result"
}
```

Use `helix logs -s agent -g conversation_id` or `-v` for correlation fields.

## When logs are written

- **CLI / TUI / `helix run`:** agent events via `wire_default_monitoring()` on `HelixAgent`
- **Gateway:** `gateway.log` on background start; agent events when API runs agents
- **Cron:** `runs.log` per job line; agent JSONL when scheduler executes jobs
- **Sub-agents:** `subagent.jsonl` on spawn and terminate

Logging is initialized on every `helix` invocation (`configure_helix_logging()` in `cli/main.py`).

## Troubleshooting

```bash
helix logs -l error -n 100
helix logs -s gateway -f
helix doctor                      # platform, PATH tools, helix home path
```

If `helix logs` shows nothing, run an agent once (`helix run "hi"`) or start the gateway.

Windows: gateway stop uses `taskkill`; optional `uv sync --extra windows` installs `psutil` for cleaner process-tree termination.

## Related

- [CLI.md](CLI.md) — full command reference
- [GATEWAY.md](GATEWAY.md) — gateway supervisor
- [CONFIGURATION.md](CONFIGURATION.md) — `HELIX_LOG_*` variables
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — common failures