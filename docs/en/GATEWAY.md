# API Gateway

OpenAI-compatible HTTP API and companion services (Telegram when configured).

## Commands

```bash
helix gateway start              # background (default host 127.0.0.1)
helix gateway start -f           # foreground
helix gateway start --reload     # dev auto-reload
helix gateway status
helix gateway stop
helix gateway reload
```

State: `~/.helix/gateway/state.json` (or `{HELIX_HOME}/gateway/`)  
Logs: `gateway/gateway.log` — view with `helix logs -s gateway -f` ([LOGS.md](LOGS.md))

The supervisor also runs **cron** and **Telegram** (when configured) as companion processes.

## Environment

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