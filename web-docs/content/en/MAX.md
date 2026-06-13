# MAX Messenger

Holix integrates with [MAX](https://max.ru) — the Russian messenger platform — so you can run the same self-improving agent in personal and group chats.

Official API reference: [dev.max.ru/docs-api](https://dev.max.ru/docs-api)

Each **host profile** can have its own bot token. Secrets are stored at:

`~/.holix/profiles/<name>/max.env`

```bash
uv sync --extra max
holix -p shared max setup          # wizard: token, mode, allowlist
holix -p shared gateway start -f   # gateway + MAX webhook (production)
```

In production (`HELIX_ENV=production`), you need an allowlist or access-request mode.

### Token storage and loading

- Store the bot token in `profiles/<host-bot>/max.env`. With [profile encryption](CONFIGURATION.md#optional-profile-encryption) enabled, the file is encrypted on disk (via shared `integrations/messenger/env_store`, same as Telegram).
- Canonical keys are `HOLIX_MAX_*`; legacy `HELIX_MAX_*` keys are supported on read and migration.
- **Do not** leave an empty `MAX_ACCESS_TOKEN=` in `global/.env` — it blocks the real token from `max.env`. Omit the key in global; Holix loads from the profile (including decrypted values when `HOLIX_UNLOCK_KEY` is set).
- On startup, the gateway calls `load_max_env_files()` after profile unlock so the encrypted token is available before webhook registration.

### Production (`uv tool install`)

When installing globally with uv, explicitly include the `max` extra:

```bash
uv tool install ~/Holix --force --with "Holix[max]"
```

Without MAX dependencies, the companion process is skipped in logs even when a token is configured.

## One bot — many users (recommended)

One MAX token serves many people. **You do not need to type user ids manually.**

### 1. Admin: connect the bot

```bash
holix -p shared max setup
HOLIX_ENV=production holix -p shared gateway start -f
```

The wizard saves the **bot token** and enables **access requests** by default (`HOLIX_MAX_ACCESS_REQUESTS=true`).

Create the bot at [business.max.ru](https://business.max.ru/self) → **Chat bots** → **Integration**, then copy the access token.

### 2. First administrator (CLI only)

The first approved user can be designated the **sole** MAX administrator. This cannot be done from MAX chat — only via CLI:

```bash
holix -p shared max requests approve USER_ID --set-admin
```

Holix will:

- create the **`admin`** Holix profile (if missing) and bind the user
- save `HOLIX_MAX_ADMIN_USER_ID` in `max.env`
- enable extended commands for that user (`/message`, `/init`, MCP install)

Check and reset:

```bash
holix -p shared max admin show
holix -p shared max admin clear   # before assigning another admin
```

### 3. User: request access

1. Open the bot in MAX.
2. Send `/start`.
3. The bot replies that access is pending approval.
4. The MAX administrator receives a **notification in MAX** with CLI commands to approve or reject.

### 4. Admin: approve and isolated profile

```bash
holix -p shared max requests list
holix -p shared max requests approve USER_ID -i              # pick or create a profile
holix -p shared max requests approve USER_ID --create-profile ivan
```

On approval, Holix:

- creates a **protected** profile `ivan` with an `hp_…` access key
- enables **workspace jail** under `~/.holix/profiles/ivan/workspace/`
- binds the MAX user to the profile
- **sends the access key to the user in MAX** (shown once)

The user can message the bot immediately — no restart required.

> **Paths in bot replies:** approved users with workspace jail see **relative paths only** (`docs/report.pdf`, not `~/.holix/profiles/ivan/workspace/…`). The **MAX admin** (`HOLIX_MAX_ADMIN_USER_ID`) still sees full absolute paths. See [Path visibility in replies](PROFILES.md#path-visibility-in-replies).

Other commands:

```bash
holix -p shared max requests approve USER_ID --profile existing   # existing open profile
holix -p shared max requests reject USER_ID
holix -p shared max status
```

### Production notes

- Use a **named host profile** (`-p shared`), not `default` — `default` is **dev-only** when `HOLIX_ENV=production`.
- Prefer `--create-profile` per user for isolation.
- Manual allowlist (`HOLIX_MAX_ALLOWED_USERS`) is optional when access requests are enabled.
- There is **only one** MAX administrator (`HOLIX_MAX_ADMIN_USER_ID`); assign via `requests approve --set-admin`.

Details: [MAX_MULTI_PROFILE.md](MAX_MULTI_PROFILE.md).

---

## Multiple bots (full isolation)

Different people → different profiles → different bots:

```bash
holix -p alice max setup
holix -p bob max setup
holix -p alice gateway start
holix -p bob gateway start
```

Each profile has its own `max.env`, webhook URL, and gateway port.

## Manual user id → profile mapping

```bash
holix -p shared max map set 123456789 alice
holix -p shared max map bind bob --user-id 987654321
holix -p shared max map list
```

Files: `profiles/shared/max-users.json`, optional `HOLIX_MAX_USER_PROFILES` in `max.env`.

One live message per task; slash commands like TUI; inline approvals for risky tools.

---

## Event delivery modes

MAX supports **one** mode at a time:

| Mode | When to use | Holix command |
|------|-------------|---------------|
| **Webhook** | Production | `holix gateway start` |
| **Long Polling** | Local development | `holix max` |

```bash
# Development (Long Polling — dev/test only):
holix max

# Production (webhook via gateway):
holix gateway start
```

The gateway registers the webhook with MAX (`POST /subscriptions`) and serves `POST /max/webhook`.

Long Polling (`GET /updates`) is rate-limited and not suitable for production. MAX recommends HTTPS webhook on port 443 with a trusted TLS certificate.

After changing `max.env` or user maps with the gateway running:

```bash
holix gateway reload
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MAX_ACCESS_TOKEN` | Yes | Bot token from business.max.ru |
| `HOLIX_MAX_ALLOWED_USERS` | Prod* | Comma-separated `user_id` allowlist |
| `HOLIX_MAX_ACCESS_REQUESTS` | No | Access requests via `/start` (default `true` in setup) |
| `HOLIX_MAX_ALLOW_ALL` | No | Allow everyone (dev only) |
| `HOLIX_MAX_MODE` | No | `webhook` (prod) or `polling` (dev/test) |
| `HOLIX_MAX_WEBHOOK_URL` | Webhook | Public HTTPS URL for events |
| `HOLIX_MAX_WEBHOOK_SECRET` | Webhook | Secret for `X-Max-Bot-Api-Secret` header |
| `HOLIX_MAX_ADMIN_USER_ID` | No | Sole MAX administrator |
| `HOLIX_MAX_PROFILE` | No | Holix host-bot profile |

\* With `HOLIX_MAX_ACCESS_REQUESTS=true`, a manual allowlist is optional.

The token is sent in the `Authorization` header — query-string tokens are **not** supported by the MAX API.

## CLI commands

| Command | Description |
|---------|-------------|
| `holix max setup` | Wizard: token, allowlist, mode, save to `profiles/{p}/max.env` |
| `holix max` | Start bot (Long Polling — dev/test only) |
| `holix max status` | Token, admin, user map, pending requests, subscriptions |
| `holix max map` | User → profile bindings |
| `holix max requests` | List/approve/reject access requests |
| `holix max admin` | Show/clear MAX administrator |
| `holix gateway start` | Gateway + MAX webhook companion |
| `holix gateway status` | Gateway health + MAX env/admin/map summary |

Management API: `GET /api/holix/profiles/{id}/max/status`, `…/requests`, `…/map`, `…/admin`.

See [CLI.md](CLI.md#holix-max).

## Features

### Agent conversations

- One live message per task (edited via `PUT /messages` while streaming)
- Session id: `max_{profile}_{user_id}`
- Shared slash commands with TUI: `/help`, `/profile`, `/models`, `/new`, `/stop` — see [SLASH_COMMANDS.md](SLASH_COMMANDS.md)

### Inline approvals

When the agent requests confirmation for a risky tool, Holix sends an inline keyboard. Button press → `message_callback` event → answer via `POST /answers`.

### Files

Send and receive attachments via `POST /uploads`. Text extraction uses the same pipeline as Telegram. The `send_chat_files` tool is available in MAX chat.

### Markdown in replies

Agent output uses MAX markdown (`**bold**`, `*italic*`, `` `code` ``, links). Long answers are split into chunks.

## Architecture

```
integrations/max/
├── client.py         # REST client (platform-api.max.ru)
├── host.py           # multi-user host, ACL, routing
├── bot.py            # event dispatcher
├── webhook.py        # FastAPI route POST /max/webhook
├── polling.py        # GET /updates loop (dev)
├── env_store.py      # profiles/<p>/max.env (messenger/env_store)
└── main.py           # holix max entry point
```

The pattern mirrors `integrations/telegram/` but uses a lightweight HTTP client (`aiohttp`) instead of aiogram.

## Production checklist

1. Public **HTTPS** endpoint on port 443 (reverse proxy → gateway)
2. `HOLIX_MAX_MODE=webhook` and a valid `HOLIX_MAX_WEBHOOK_URL`
3. Allowlist or access requests; `HOLIX_ENV=production`
4. MAX rate limit: **30 rps** on `platform-api.max.ru`

See [DEPLOYMENT.md](DEPLOYMENT.md) and [SECURITY.md](SECURITY.md).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401` from MAX API | Check `MAX_ACCESS_TOKEN`; re-run `holix max setup` |
| No webhook events | Verify HTTPS URL, `POST /subscriptions`, gateway logs |
| Polling stopped after webhook | Only one mode is active — remove webhook subscription first |
| User ignored | Approve via `holix max requests approve` or add to allowlist |
| Agent cannot send files | `uv sync --extra max`; use `send_chat_files` in MAX chat |
| `429` errors | Reduce send rate; Holix client limits to ≤30 rps |

Run `holix doctor` to check token, webhook, and allowlist.

## See also

- [MAX_MULTI_PROFILE.md](MAX_MULTI_PROFILE.md) — one bot / multiple bots, isolation
- [TELEGRAM.md](TELEGRAM.md) — parallel Telegram integration
- [GATEWAY.md](GATEWAY.md) — HTTP gateway and companions
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — `/` commands in MAX chats