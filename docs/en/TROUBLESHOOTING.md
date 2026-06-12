# Troubleshooting

## Gateway won't start

```bash
holix doctor
holix gateway status
holix logs -s gateway -n 50
# or: cat ~/.holix/gateway/gateway.log
```

On Windows, check port binding: `netstat -ano | findstr :8000` (hint from `holix gateway start` on failure).

## No agent output / silent failures

```bash
holix logs -l error -n 100
holix logs -s agent -f
holix logs debug on
holix run "test"
```

## Windows-specific

- Terminal tool uses **cmd** builtins (`dir`, `type`, `where`); Unix commands (`ls`, `grep`) are blocked unless added via `holix profile whitelist add` or `HOLIX_TERMINAL_WHITELIST_EXTRA` in the profile `.env`
- Sub-agents run in **async** mode (not separate OS processes)
- Data dir: `%LOCALAPPDATA%\Holix` unless `HOLIX_HOME` is set
- Optional: `uv sync --extra windows` for improved process cleanup (`psutil`)

## Dishka / agent init error

Ensure profile loads: `holix doctor --fix`

## LLM connection failed

```bash
holix models setup
ollama serve
holix doctor
```

## Telegram access denied

1. User must send **`/start`** first (access-request mode).
2. Designate a Telegram admin (once): `holix -p shared telegram requests approve USER_ID --set-admin`.
3. Admin approves new users: `holix -p shared telegram requests list` → `telegram requests approve USER_ID -i` or `--create-profile NAME`.
4. For a personal bot, set `HOLIX_TELEGRAM_ALLOWED_USERS` to your numeric user id.
5. In production use a **named** profile (`-p shared`), not `default`.

## Telegram menu visible before approval

Slash commands are hidden until the user is approved (or on allowlist / `map`). After approve, run `holix telegram sync-menu` if the client still shows an old global menu.

See [TELEGRAM.md](TELEGRAM.md).

## Auth 401 on API

Set `Authorization: Bearer <key>` or `X-API-Key`. Create admin key via `/admin/api-keys` (requires admin key when auth enabled).

## Related

- [LOGS.md](LOGS.md) — log files, filters, rotation, debug mode