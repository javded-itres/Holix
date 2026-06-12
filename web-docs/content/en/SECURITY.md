# Security

## Production checklist

1. `HOLIX_ENV=production`
2. `HOLIX_REQUIRE_AUTH=true` (forced in production)
3. `HOLIX_API_KEY_PEPPER` — long random secret
4. `HOLIX_CORS_ORIGINS` — explicit origins (no `*`)
5. `HOLIX_GATEWAY_HOST=127.0.0.1` behind reverse proxy with TLS
6. Telegram: `HOLIX_TELEGRAM_ACCESS_REQUESTS=true` (default after `telegram setup`) or `HOLIX_TELEGRAM_ALLOWED_USERS` for a personal bot; use named profiles (`-p shared`), not `default`, in production
7. `HOLIX_ENABLE_CODE_EXECUTOR=false` if not required
8. `HOLIX_TERMINAL_COMMAND_WHITELIST=true`

## Web TUI (`holix tui --web`)

The browser UI runs a full Holix agent (terminal tool, files, MCP). Treat it like root on your machine.

| Bind | Requirements |
|------|----------------|
| `127.0.0.1` (default) | Token via `--token`, `HOLIX_TUI_WEB_TOKEN`, or ephemeral `--generate-token` (default) |
| `0.0.0.0` / LAN | `--allow-lan` **and** explicit `--token` / env (no auto-generated token) |
| `HOLIX_ENV=production` | Explicit token always |

- Do not expose port 8787 to the internet without TLS and a reverse proxy.
- Rotate tokens after sharing a LAN URL.

## API keys

- Stored as HMAC-SHA256 with pepper
- Admin endpoints always require `admin` permission
- Create keys via `POST /admin/api-keys` with admin key (no `holix` CLI command for `hx_` keys yet — use curl or Swagger `/docs`)

### Two-layer gateway auth

The gateway uses **two independent credentials**:

| Layer | Key | Prefix | Purpose |
|-------|-----|--------|---------|
| 1 — Gateway API key | `Authorization: Bearer …` or `X-API-Key` | `hx_…` | Authenticates every protected HTTP route (chat, Hermes, management) |
| 2 — Profile access key | `X-Holix-Profile-Key` | `hp_…` | Authorizes `/api/holix/*` management for a specific profile |

**Layer 1** is always required when `HOLIX_REQUIRE_AUTH=true` (except `/health`, `/v1/health`). Create `hx_` keys via `POST /admin/api-keys`.

**Layer 2** applies to `/api/holix/*` only. A profile owner sends their `hp_…` key to manage their own profile. Gateway admins bypass layer 2 with an API key that has `admin` permission, or with the master key of the admin profile (`HOLIX_TELEGRAM_ADMIN_PROFILE`, default `admin`). Create `hp_` keys via `holix profile key init` — not via the gateway admin API.

Chat and Hermes routes (`/v1/chat/completions`, `/v1/models`, etc.) need **layer 1 only**. Profile routing uses `X-Holix-Profile` or the `model` field — not `hp_`.

Full tables: [GATEWAY_API.md](GATEWAY_API.md#authentication).

### Docs-chat token (separate surface)

When the documentation site runs with `--with-docs` and `HOLIX_DOCS_CHAT_ENABLED=1`, the embedded docs assistant uses **`HOLIX_DOCS_CHAT_TOKEN`** — a dedicated secret for `/v1/docs/chat` and the docs-server proxy (`/api/docs-chat`).

This token is **not** a gateway API key (`hx_`) and **not** a profile key (`hp_`). It is server-side only (proxy holds the token; the browser never sees it). Rotate independently from gateway keys.

## Profile secrets

In `~/.holix/profiles/<name>/config.yaml`:

```yaml
api_key: ${OPENAI_API_KEY}
```

Never commit real keys to git.

## Tools

- **Terminal**: whitelist, dangerous-pattern blocks, and confirmations — full guide: [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md). Quick setup:
  ```bash
  holix -p dev profile whitelist enable
  holix -p dev profile whitelist add "docker, make"
  holix -p dev profile whitelist list
  ```
- **Python executor**: disable in production via `HOLIX_ENABLE_CODE_EXECUTOR=false`

## Run audit

```bash
holix doctor
holix doctor --fix
```