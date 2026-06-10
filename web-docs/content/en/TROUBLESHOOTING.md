# Troubleshooting

## Gateway won't start

```bash
helix doctor
helix gateway status
helix logs -s gateway -n 50
# or: cat ~/.helix/gateway/gateway.log
```

On Windows, check port binding: `netstat -ano | findstr :8000` (hint from `helix gateway start` on failure).

## No agent output / silent failures

```bash
helix logs -l error -n 100
helix logs -s agent -f
helix logs debug on
helix run "test"
```

## Windows-specific

- Terminal tool uses **cmd** builtins (`dir`, `type`, `where`); Unix commands (`ls`, `grep`) are blocked unless added via `helix profile whitelist add` or `HELIX_TERMINAL_WHITELIST_EXTRA` in the profile `.env`
- Sub-agents run in **async** mode (not separate OS processes)
- Data dir: `%LOCALAPPDATA%\Helix` unless `HELIX_HOME` is set
- Optional: `uv sync --extra windows` for improved process cleanup (`psutil`)

## Dishka / agent init error

Ensure profile loads: `helix doctor --fix`

## LLM connection failed

```bash
helix models setup
ollama serve
helix doctor
```

## Telegram access denied

Set `HELIX_TELEGRAM_ALLOWED_USERS` to your numeric user id.

## Auth 401 on API

Set `Authorization: Bearer <key>` or `X-API-Key`. Create admin key via `/admin/api-keys` (requires admin key when auth enabled).

## Related

- [LOGS.md](LOGS.md) — log files, filters, rotation, debug mode