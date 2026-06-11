# Security

## Production checklist

1. `HELIX_ENV=production`
2. `HELIX_REQUIRE_AUTH=true` (forced in production)
3. `HELIX_API_KEY_PEPPER` — long random secret
4. `HELIX_CORS_ORIGINS` — explicit origins (no `*`)
5. `HELIX_GATEWAY_HOST=127.0.0.1` behind reverse proxy with TLS
6. Telegram: `HELIX_TELEGRAM_ACCESS_REQUESTS=true` (default after `telegram setup`) or `HELIX_TELEGRAM_ALLOWED_USERS` for a personal bot; use named profiles (`-p shared`), not `default`, in production
7. `HELIX_ENABLE_CODE_EXECUTOR=false` if not required
8. `HELIX_TERMINAL_COMMAND_WHITELIST=true`

## Web TUI (`helix tui --web`)

The browser UI runs a full Helix agent (terminal tool, files, MCP). Treat it like root on your machine.

| Bind | Requirements |
|------|----------------|
| `127.0.0.1` (default) | Token via `--token`, `HELIX_TUI_WEB_TOKEN`, or ephemeral `--generate-token` (default) |
| `0.0.0.0` / LAN | `--allow-lan` **and** explicit `--token` / env (no auto-generated token) |
| `HELIX_ENV=production` | Explicit token always |

- Do not expose port 8787 to the internet without TLS and a reverse proxy.
- Rotate tokens after sharing a LAN URL.

## API keys

- Stored as HMAC-SHA256 with pepper
- Admin endpoints always require `admin` permission
- Create keys via `POST /admin/api-keys` with admin key (no `helix` CLI command for `hx_` keys yet — use curl or Swagger `/docs`)

### Two-layer gateway auth

The gateway uses **two independent credentials**:

| Layer | Key | Prefix | Purpose |
|-------|-----|--------|---------|
| 1 — Gateway API key | `Authorization: Bearer …` or `X-API-Key` | `hx_…` | Authenticates every protected HTTP route (chat, Hermes, management) |
| 2 — Profile access key | `X-Helix-Profile-Key` | `hp_…` | Authorizes `/api/helix/*` management for a specific profile |

**Layer 1** is always required when `HELIX_REQUIRE_AUTH=true` (except `/health`, `/v1/health`). Create `hx_` keys via `POST /admin/api-keys`.

**Layer 2** applies to `/api/helix/*` only. A profile owner sends their `hp_…` key to manage their own profile. Gateway admins bypass layer 2 with an API key that has `admin` permission, or with the master key of the admin profile (`HELIX_TELEGRAM_ADMIN_PROFILE`, default `admin`). Create `hp_` keys via `helix profile key init` — not via the gateway admin API.

Chat and Hermes routes (`/v1/chat/completions`, `/v1/models`, etc.) need **layer 1 only**. Profile routing uses `X-Helix-Profile` or the `model` field — not `hp_`.

Full tables: [GATEWAY_API.md](GATEWAY_API.md#authentication).

### Docs-chat token (separate surface)

When the documentation site runs with `--with-docs` and `HELIX_DOCS_CHAT_ENABLED=1`, the embedded docs assistant uses **`HELIX_DOCS_CHAT_TOKEN`** — a dedicated secret for `/v1/docs/chat` and the docs-server proxy (`/api/docs-chat`).

This token is **not** a gateway API key (`hx_`) and **not** a profile key (`hp_`). It is server-side only (proxy holds the token; the browser never sees it). Rotate independently from gateway keys.

## Profile secrets

In `~/.helix/profiles/<name>/config.yaml`:

```yaml
api_key: ${OPENAI_API_KEY}
```

Never commit real keys to git.

## Tools

- **Terminal**: whitelist, dangerous-pattern blocks, and confirmations — full guide: [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md). Quick setup:
  ```bash
  helix -p dev profile whitelist enable
  helix -p dev profile whitelist add "docker, make"
  helix -p dev profile whitelist list
  ```
- **Python executor**: disable in production via `HELIX_ENABLE_CODE_EXECUTOR=false`

## Run audit

```bash
helix doctor
helix doctor --fix
```