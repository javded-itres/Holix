# Security

## Production checklist

1. `HELIX_ENV=production`
2. `HELIX_REQUIRE_AUTH=true` (forced in production)
3. `HELIX_API_KEY_PEPPER` — long random secret
4. `HELIX_CORS_ORIGINS` — explicit origins (no `*`)
5. `HELIX_GATEWAY_HOST=127.0.0.1` behind reverse proxy with TLS
6. `HELIX_TELEGRAM_ALLOWED_USERS` set when using Telegram
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
- Create keys via `POST /admin/api-keys` with admin key

## Profile secrets

In `~/.helix/profiles/<name>/config.yaml`:

```yaml
api_key: ${OPENAI_API_KEY}
```

Never commit real keys to git.

## Tools

- **Terminal**: whitelist enforced when `HELIX_TERMINAL_COMMAND_WHITELIST=true` (default). Manage per profile:
  ```bash
  helix -p dev profile whitelist enable
  helix -p dev profile whitelist add "docker, make"
  helix -p dev profile whitelist list
  ```
  Or set `HELIX_TERMINAL_WHITELIST_EXTRA` in `profiles/<name>/.env`.
- **Python executor**: disable in production via `HELIX_ENABLE_CODE_EXECUTOR=false`

## Run audit

```bash
helix doctor
helix doctor --fix
```