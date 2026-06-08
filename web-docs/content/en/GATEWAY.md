# API Gateway

OpenAI-compatible HTTP API and companion services (Telegram when configured).

## Commands

Gateway commands apply to the **active profile** (`-p` / `--profile`).

```bash
helix -p alice gateway start              # background (default host 127.0.0.1)
helix -p alice gateway start -f           # foreground
helix -p alice gateway start --reload     # dev auto-reload
helix -p alice gateway status
helix -p alice gateway stop
helix -p alice gateway reload
```

Each profile has its own gateway state and logs:

- State: `~/.helix/profiles/<name>/gateway/state.json`
- Logs: `~/.helix/profiles/<name>/gateway/gateway.log` — `helix logs -s gateway -f` ([LOGS.md](LOGS.md))

**Multiple gateways** can run at once (different profiles, different ports):

```bash
# profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# profiles/bob/.env
HELIX_GATEWAY_PORT=8002

helix -p alice gateway start
helix -p bob gateway start
```

The supervisor also runs **cron** and **Telegram** (when configured for that profile) as companion processes.

## Environment

Set bind address and port in the **profile** `.env` (`helix profile env --edit`):

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_GATEWAY_HOST` | `127.0.0.1` | Bind address |
| `HELIX_GATEWAY_PORT` | `8000` | Port |
| `HELIX_REQUIRE_AUTH` | `false` | API key for `/v1/*` |
| `HELIX_ENV=production` | — | Forces auth + stricter checks |

Admin routes (`/admin/*`) **always** require an admin API key.

## Endpoints

- `GET /health` — health check
- `GET /metrics` — Prometheus text metrics
- `POST /v1/chat/completions` — OpenAI-compatible chat
- `POST /admin/api-keys` — create API key (admin)

Create first admin key (with auth enabled):

```bash
# Bootstrap: temporarily set HELIX_REQUIRE_AUTH=false, create key with permissions admin, then enable auth
```