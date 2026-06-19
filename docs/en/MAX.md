# MAX Messenger

Holix integrates with [MAX](https://max.ru) — the Russian messenger platform — so you can run the same self-improving agent in personal and group chats.

Official API reference: [dev.max.ru/docs-api](https://dev.max.ru/docs-api)

Each **host profile** can have its own bot token. Secrets are stored at:

`~/.holix/profiles/<name>/max.env`

```bash
uv sync --extra max
holix -p shared max setup          # wizard: token, mode, allowlist
holix -p shared gateway start        # gateway + MAX (polling in dev, webhook in prod)
```

In production (`HELIX_ENV=production`), you need an allowlist or access-request mode.

---

## Complete guide: bot registration and environment variables

Step-by-step from creating a bot in the MAX business console to a working agent in chat.

### Prerequisites

| Requirement | Why |
|-------------|-----|
| Organization account at [business.max.ru](https://business.max.ru/self) | Required to issue a bot access token |
| Holix installed with the `max` extra | HTTP client, polling, webhook |
| A Holix **host profile** for the bot | Usually `shared` or `admin` — not `default` in production |
| LLM configured in that profile | `holix models setup` or keys in `profiles/<name>/.env` |

Secrets file:

`~/.holix/profiles/<host-profile>/max.env`

Example for host profile `shared`: `~/.holix/profiles/shared/max.env`.

### Step 1. Create the bot in the MAX console

1. Open [business.max.ru/self](https://business.max.ru/self) and sign in with your organization account.
2. Go to **Chat bots** (or **Bots** / **Integration** — labels may vary).
3. Click **Create bot** / **Add bot**.
4. Fill in the bot card:
   - **Name** — how users see the bot in MAX.
   - **Description** — short purpose (optional).
   - **Avatar** — optional.
5. Open the **Integration** tab (or **API** / **Access token**).
6. Copy the **Access token**.  
   Treat it like a password — do not commit it to git or paste in public chats.
7. Ensure the bot is **published** / **enabled** if the console has an activity toggle.

Official API docs: [dev.max.ru/docs-api](https://dev.max.ru/docs-api).

> **Note:** the token is sent in the `Authorization` header to `platform-api.max.ru`. The MAX API does **not** accept tokens in query strings.

### Step 2. Find your MAX user id

The user id is a numeric MAX account identifier. You need it for the allowlist and admin assignment.

**Option A — Holix wizard (recommended):**

```bash
holix -p shared max setup
```

When asked for your MAX user id, choose auto-detection: send any message to the bot in MAX — Holix will capture the id from the event stream.

**Option B — manually:**

- Read the id from a notification after `/start` if the bot already runs with access requests.
- Or use `holix max requests list` after a user applies — entries include `user_id`.

Config format: a single number or comma-separated list: `123456789` or `111,222,333`.

### Step 3. Install dependencies and run the wizard

```bash
# from the Holix repo
uv sync --extra max

# global install (production)
uv tool install ~/Holix --force --with "Holix[max]"
```

Interactive setup:

```bash
holix -p shared max setup
```

The wizard:

1. Verifies the token (`GET /me` against the MAX API).
2. Asks for an allowlist (your user id) or detects it automatically.
3. Chooses the Holix host profile (`HOLIX_MAX_PROFILE`).
4. Chooses mode: `polling` (development) or `webhook` (production).
5. For webhook — asks for a public HTTPS URL and secret.
6. Saves everything to `~/.holix/profiles/shared/max.env`.
7. Enables **access requests** by default (`HOLIX_MAX_ACCESS_REQUESTS=true`).

Verify:

```bash
holix -p shared max status
holix doctor
```

### Step 4. Start the bot

| Environment | `HOLIX_MAX_MODE` | Command |
|-------------|------------------|---------|
| Development (`HOLIX_ENV` ≠ `production`) | `polling` (default) | `holix -p shared gateway start` |
| Production | `webhook` (forced) | `holix -p shared gateway start -f` |

In **development**, the gateway starts MAX Long Polling as a companion — a separate `holix max` process is optional.

In **production**, you need public HTTPS and `HOLIX_MAX_WEBHOOK_URL` (see example below).

```bash
# local development
holix -p shared gateway start

# production (named profile + production env)
HOLIX_ENV=production holix -p shared gateway start -f
```

Check status:

```bash
holix -p shared gateway status
```

### Step 5. Manual `max.env` configuration

If you prefer not to use the wizard, create or edit the file manually.

**Development (polling, access requests):**

```env
# ~/.holix/profiles/shared/max.env
# Holix MAX — manual configuration

MAX_ACCESS_TOKEN=your_token_from_business_max_ru

# Delivery mode: polling in dev (gateway starts the companion)
HOLIX_MAX_MODE=polling

# Holix profile for the host bot (token, user map)
HOLIX_MAX_PROFILE=shared

# New users request access via /start (recommended)
HOLIX_MAX_ACCESS_REQUESTS=true

# Your user id (optional with access requests — approve via CLI)
HOLIX_MAX_ALLOWED_USERS=123456789

# Local testing only — NOT for production:
# HOLIX_MAX_ALLOW_ALL=true
```

**Production (webhook):**

```env
# ~/.holix/profiles/shared/max.env

MAX_ACCESS_TOKEN=your_token_from_business_max_ru

HOLIX_MAX_MODE=webhook
HOLIX_MAX_PROFILE=shared
HOLIX_MAX_ACCESS_REQUESTS=true

# Public URL where MAX sends events (HTTPS, port 443)
# Typically: https://your-domain/max/webhook
HOLIX_MAX_WEBHOOK_URL=https://agent.example.com/max/webhook

# Secret for X-Max-Bot-Api-Secret header (use a long random string)
HOLIX_MAX_WEBHOOK_SECRET=random_string_at_least_32_chars

# Admin is assigned via CLI; leave empty until first approve --set-admin
# HOLIX_MAX_ADMIN_USER_ID=123456789
# HOLIX_MAX_ADMIN_PROFILE=admin
```

After editing `max.env` while the gateway is running:

```bash
holix -p shared gateway reload
```

### Full variable reference

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `MAX_ACCESS_TOKEN` | **Yes** | `AbCdEf…` | Bot token from business.max.ru → Integration. Canonical key; legacy: `HOLIX_MAX_ACCESS_TOKEN`. |
| `HOLIX_MAX_PROFILE` | No | `shared` | Holix host-bot profile (where `max.env` and user map live). Defaults to active `-p` profile. |
| `HOLIX_MAX_MODE` | No | `polling` / `webhook` | Event delivery mode. Forced to `webhook` when `HOLIX_ENV=production`. |
| `HOLIX_MAX_WEBHOOK_URL` | Webhook | `https://host/max/webhook` | Public HTTPS endpoint on the Holix gateway (`POST /max/webhook`). |
| `HOLIX_MAX_WEBHOOK_SECRET` | Webhook* | `my-secret-…` | Secret for `X-Max-Bot-Api-Secret`. Recommended in production. |
| `HOLIX_MAX_ACCESS_REQUESTS` | No | `true` | Users send `/start`; admin approves via CLI. Default `true` in `max setup`. |
| `HOLIX_MAX_ALLOWED_USERS` | Prod** | `123,456` | Allowlist: only these `user_id` values may use the bot (without access requests). |
| `HOLIX_MAX_ALLOW_ALL` | No | `true` | Allow everyone without checks. **Dev only.** |
| `HOLIX_MAX_ADMIN_USER_ID` | No | `123456789` | Sole MAX administrator. Set via `max requests approve ID --set-admin`. |
| `HOLIX_MAX_ADMIN_PROFILE` | No | `admin` | Holix profile for the admin (usually `admin`). |
| `HOLIX_MAX_USER_PROFILES` | No | `111:alice,222:bob` | Static `user_id` → profile map (alternative to `max-users.json`). |
| `HOLIX_MAX_POLL_TIMEOUT` | No | `5` | Long-poll timeout in seconds (0–90). |
| `HOLIX_MAX_EDIT_INTERVAL_MS` | No | `1500` | Live message edit interval (ms). |
| `HOLIX_MAX_HEARTBEAT_INTERVAL` | No | `45` | Heartbeat interval for long-running tasks (s). |

\* Webhook may work without a secret, but production should set one.  
\*\* With `HOLIX_MAX_ACCESS_REQUESTS=true`, a manual allowlist is optional.

**Related files (not in `max.env`):**

| File | Purpose |
|------|---------|
| `profiles/<host>/max-users.json` | MAX user id → Holix profile bindings |
| `profiles/<host>/max-access-requests.json` | Pending access request queue |
| `profiles/<host>/.env` | LLM, gateway, encryption — separate from the bot token |

**Do not:**

- Leave an empty `MAX_ACCESS_TOKEN=` in `global/.env` — it overrides the real token from `max.env`.
- Use `HOLIX_MAX_ALLOW_ALL=true` in production.
- Store the token in git; with profile encryption, `max.env` is encrypted on disk automatically.

### Common configuration mistakes

| Mistake | Fix |
|---------|-----|
| `401` from MAX API | Check token; re-issue in console; run `holix max setup` |
| Bot silent in dev | Run `holix gateway start`; check `holix max status` → Mode: polling |
| No webhook events | HTTPS on 443, correct URL, `holix gateway status`, gateway logs |
| “Access denied” | `holix max requests approve` or add id to allowlist |
| Both modes active | Only polling **or** webhook — remove webhook subscription before polling |

---

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

---

## Multi-profile topologies

Each profile has isolated `.env`, `max.env`, gateway, and memory. See [PROFILES.md](PROFILES.md).

**Rule:** one MAX bot token = one host profile = one webhook (or one polling process).

| Approach | Isolation | Setup |
|----------|-----------|-------|
| **One bot per profile** | Full | Separate token + gateway per profile |
| **One bot + access requests** | Per-user profile + jail | § One bot — many users above |
| **One bot + `map`** | Manual bindings | `holix max map set …` |

### One bot per profile

```bash
holix -p alice max setup
holix -p bob max setup
holix -p alice gateway start
holix -p bob gateway start
```

Different `HOLIX_GATEWAY_PORT` and `HOLIX_MAX_WEBHOOK_URL` per profile in `.env` / `max.env`.

### Common mistakes

- Same token in multiple `max.env` files.
- Same gateway port across profiles.
- Production without allowlist or access requests.

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

| Mode | When to use | How Holix starts it |
|------|-------------|---------------------|
| **Webhook** | Production (`HOLIX_ENV=production`) | `holix gateway start` — registered inside gateway |
| **Long Polling** | Local development | `holix gateway start` — polling companion in gateway |

```bash
# Development (polling via gateway — recommended):
holix -p shared gateway start

# Alternative: bot only, without API gateway
holix -p shared max

# Production (webhook via gateway):
HOLIX_ENV=production holix -p shared gateway start -f
```

In development the gateway **automatically** starts MAX Long Polling (like the Telegram companion). Run `holix max` separately only if the API gateway is not running.

In production the gateway registers the webhook with MAX (`POST /subscriptions`) and serves `POST /max/webhook`.

Long Polling (`GET /updates`) is rate-limited and not suitable for production. MAX recommends HTTPS webhook on port 443 with a trusted TLS certificate.

After changing `max.env` or user maps with the gateway running:

```bash
holix gateway reload
```

## Environment variables

Short reference. Full guide with examples: [Complete guide](#complete-guide-bot-registration-and-environment-variables) above.

| Variable | Required | Description |
|----------|----------|-------------|
| `MAX_ACCESS_TOKEN` | Yes | Bot token from business.max.ru |
| `HOLIX_MAX_PROFILE` | No | Holix host-bot profile |
| `HOLIX_MAX_MODE` | No | `polling` (dev) or `webhook` (prod) |
| `HOLIX_MAX_WEBHOOK_URL` | Webhook | Public HTTPS URL (`/max/webhook`) |
| `HOLIX_MAX_WEBHOOK_SECRET` | Webhook | `X-Max-Bot-Api-Secret` value |
| `HOLIX_MAX_ACCESS_REQUESTS` | No | Access via `/start` (default `true`) |
| `HOLIX_MAX_ALLOWED_USERS` | Prod* | Comma-separated `user_id` allowlist |
| `HOLIX_MAX_ALLOW_ALL` | No | Allow everyone (dev only) |
| `HOLIX_MAX_ADMIN_USER_ID` | No | Sole MAX administrator |
| `HOLIX_MAX_ADMIN_PROFILE` | No | Holix admin profile (usually `admin`) |
| `HOLIX_MAX_USER_PROFILES` | No | Inline `user_id:profile` map |

\* With `HOLIX_MAX_ACCESS_REQUESTS=true`, a manual allowlist is optional.

The token is sent in the `Authorization` header — query-string tokens are **not** supported by the MAX API.

## CLI commands

| Command | Description |
|---------|-------------|
| `holix max setup` | Wizard: token, allowlist, mode, save to `profiles/{p}/max.env` |
| `holix max` | Bot only (polling), without API gateway |
| `holix max status` | Token, admin, user map, pending requests, subscriptions |
| `holix max map` | User → profile bindings |
| `holix max requests` | List/approve/reject access requests |
| `holix max admin` | Show/clear MAX administrator |
| `holix gateway start` | Gateway + MAX (polling in dev, webhook in prod) |
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

- Multi-profile topologies — § above in this page
- [TELEGRAM.md](TELEGRAM.md) — parallel Telegram integration
- [GATEWAY.md](GATEWAY.md) — HTTP gateway and companions
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — `/` commands in MAX chats