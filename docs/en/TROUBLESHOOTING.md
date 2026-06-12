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

## Workspace paths: `[restricted]` or relative paths only

**Expected behavior** when [workspace jail](PROFILES.md#workspace-jail-directory-isolation) is enabled and the caller is **not** an administrator:

- Agent replies and tool output show paths like `docs/file.txt` or `.` (jail root), not `/home/…/.holix/profiles/…`.
- Paths outside the jail appear as `[restricted]`.

**Not a bug** if a Telegram user or API client without `admin` never sees host absolute paths.

To show full paths you must be:

| Surface | Requirement |
|---------|-------------|
| Telegram | Your numeric user id equals `HOLIX_TELEGRAM_ADMIN_USER_ID` (set via `telegram requests approve … --set-admin`) |
| Gateway API | API key `permissions` include `admin` (create via `POST /admin/api-keys`) |
| Local CLI on server | Operator session without jail, or jail disabled for that profile |

Check jail status: `holix -p NAME profile jail status`. Full guide: [Path visibility in responses](PROFILES.md#path-visibility-in-responses).

## Admin still sees relative paths in Telegram

1. Confirm admin assignment: `holix -p shared telegram admin show` — must list your Telegram user id.
2. Re-assign if needed: `holix -p shared telegram requests approve USER_ID --set-admin` (CLI only).
3. Only the **single** stored admin gets full paths; other approved users remain relative-only.

## Admin still sees relative paths via API

1. Inspect key permissions: `GET /admin/api-keys` (admin key required) — entry must include `"admin"` in `permissions`.
2. Recreate key with admin if needed:
   ```bash
   curl -sS -X POST "$HOLIX_URL/admin/api-keys" \
     -H "Authorization: Bearer $ADMIN_KEY" \
     -d "name=ops-admin&permissions=read,write,execute,admin&rate_limit=1000"
   ```
3. Profile must have `workspace_jail_enabled: true`; without jail, all callers see full paths.

## Related

- [LOGS.md](LOGS.md) — log files, filters, rotation, debug mode