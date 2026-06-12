# Logs and observability

Holix writes structured logs under the data directory. Use **`holix logs`** to view, filter, rotate, and toggle debug mode.

## Data directory

| OS | Default path |
|----|----------------|
| Linux / macOS | `~/.holix/` |
| Windows | `%LOCALAPPDATA%\Holix\` |
| Override | `HOLIX_HOME=/path/to/data` |
| Linux (XDG) | `$XDG_DATA_HOME/holix/` if `HOLIX_HOME` unset |

Logs live in `{HOLIX_HOME}/logs/` unless noted.

## Log files

| File | Source | Content |
|------|--------|---------|
| `logs/agent.jsonl` | Main agent | Tool calls, errors, final responses, skills, context events (JSON lines) |
| `logs/agent.debug.jsonl` | Agent (debug) | Same events when debug mode is on |
| `logs/subagent.jsonl` | Sub-agents | Spawn, terminate, task preview |
| `logs/holix.log` | System | Python root logger (rotating) |
| `gateway/gateway.log` | Gateway | Uvicorn / API supervisor |
| `profiles/<p>/data/cron/runs.log` | Cron | Scheduled job run lines |
| `logs/hub-autoupdate.log` | Hub | Optional autoupdate output |
| `logs/history_<profile>.txt` | Chat REPL | prompt_toolkit input history (not agent output) |

Agent and sub-agent **results** appear in `agent.jsonl` (`FinalResponseEvent`, tool results) and in conversation memory; cron summaries may also post to the bound TUI/Telegram session.

## `holix logs` commands

```bash
holix logs                          # last 80 lines, all sources
holix logs show -n 200              # more lines
holix logs -s agent                 # agent JSONL only
holix logs -s gateway               # gateway.log
holix logs -s cron -p work        # cron runs for profile
holix logs -s subagent              # sub-agent events
holix logs -s system                # holix.log
holix logs -l error                 # ERROR and above
holix logs -l warning               # WARNING and above
holix logs -g "Tool call"           # text filter
holix logs -f                       # follow (stream new lines)
holix logs --debug -v               # include debug file + extra fields
holix logs list                     # files and sizes
holix logs rotate                   # rotate oversized logs + purge old backups
holix logs debug on                 # enable debug (persisted)
holix logs debug off
holix logs debug status
```

### Source filter (`-s` / `--source`)

| Value | Files |
|-------|--------|
| `all` | All existing log files (default) |
| `agent` | `agent.jsonl`, `agent.debug.jsonl` |
| `gateway` | `gateway/gateway.log` |
| `cron` | `profiles/<profile>/data/cron/runs.log` |
| `subagent` | `subagent.jsonl` |
| `system` | `holix.log`, `hub-autoupdate.log` |

## Debug mode

Debug is **off** by default. When enabled:

- Extra detail is written to `logs/agent.debug.jsonl`
- Sub-agent debug lines are duplicated there
- Root log level becomes `DEBUG`
- State is stored in `logs/logging.json` (survives restarts)

```bash
holix logs debug on
# or in .env:
# HOLIX_LOG_DEBUG=true
```

CLI debug toggle and `.env` are combined: either can enable debug.

## Rotation and retention

Configured via environment (see [CONFIGURATION.md](CONFIGURATION.md#logging)):

| Variable | Default | Meaning |
|----------|---------|---------|
| `HOLIX_LOG_MAX_BYTES` | `10485760` (10 MiB) | Rotate when file exceeds size |
| `HOLIX_LOG_BACKUP_COUNT` | `10` | Keep N rotated backups (`.1`, `.2`, …) |
| `HOLIX_LOG_ROTATION_DAYS` | `14` | Delete backups older than N days (`holix logs rotate --purge`) |

Manual rotation:

```bash
holix logs rotate
holix logs rotate --no-purge   # rotate only, keep old backups
```

`holix.log` and `subagent.jsonl` use Python `RotatingFileHandler` automatically. `holix logs rotate` handles other files by size.

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

Use `holix logs -s agent -g conversation_id` or `-v` for correlation fields.

## When logs are written

- **CLI / TUI / `holix run`:** agent events via `wire_default_monitoring()` on `HolixAgent`
- **Gateway:** `gateway.log` on background start; agent events when API runs agents
- **Cron:** `runs.log` per job line; agent JSONL when scheduler executes jobs
- **Sub-agents:** `subagent.jsonl` on spawn and terminate

Logging is initialized on every `holix` invocation (`configure_holix_logging()` in `cli/main.py`).

## Troubleshooting

```bash
holix logs -l error -n 100
holix logs -s gateway -f
holix doctor                      # platform, PATH tools, holix home path
```

If `holix logs` shows nothing, run an agent once (`holix run "hi"`) or start the gateway.

Windows: gateway stop uses `taskkill`; optional `uv sync --extra windows` installs `psutil` for cleaner process-tree termination.

## Related

- [CLI.md](CLI.md) — full command reference
- [GATEWAY.md](GATEWAY.md) — gateway supervisor
- [CONFIGURATION.md](CONFIGURATION.md) — `HOLIX_LOG_*` variables
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — common failures