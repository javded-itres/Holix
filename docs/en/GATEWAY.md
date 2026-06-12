# API Gateway

OpenAI-compatible HTTP API, Hermes-compatible surface, Holix Management API, and companion services (Telegram + cron when configured).

**Full API reference:** [GATEWAY_API.md](GATEWAY_API.md) — Hermes mapping, `/api/holix/` management, auth, SaaS curl examples.

## Commands

Gateway commands apply to the **active profile**. For `default`, omit `-p`:

```bash
holix gateway start              # background (default host 127.0.0.1)
holix gateway start -f           # foreground
holix gateway start --reload     # dev auto-reload
holix gateway status
holix gateway stop
holix gateway reload
```

Other profiles: `holix -p alice gateway start`, etc.

Each profile has its own gateway state and logs:

- State: `~/.holix/profiles/<name>/gateway/state.json`
- Logs: `~/.holix/profiles/<name>/gateway/gateway.log` — `holix logs -s gateway -f` ([LOGS.md](LOGS.md))

**Multiple gateways** can run at once (different profiles, different ports):

```bash
# profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# profiles/bob/.env
HOLIX_GATEWAY_PORT=8002

holix -p alice gateway start
holix -p bob gateway start
```

The supervisor also runs **cron** and **Telegram** (when configured for that profile) as companion processes.

## Multi-profile gateway (v0.2+)

A single uvicorn process can serve **multiple Holix profiles**:

- Profile routing: `X-Holix-Profile` → `model` field → host profile
- Per-profile reload: `POST /api/holix/profiles/{id}/reload` (agent + Telegram + cron)
- Management API: `/api/holix/` for profiles, models, MCP, skills, Telegram admin

See [GATEWAY_API.md](GATEWAY_API.md) for endpoint tables and authentication.

## Environment

Set bind address and port in the **profile** `.env` (`holix profile env --edit`):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOLIX_GATEWAY_HOST` | `127.0.0.1` | Bind address |
| `HOLIX_GATEWAY_PORT` | `8000` | Port |
| `HOLIX_REQUIRE_AUTH` | `true` | API key required (except `/health`, `/v1/health`) |
| `HOLIX_ENV=production` | — | Forces auth + stricter checks |

Admin routes (`/admin/*`) **always** require an admin API key.

## Quick endpoint map

| Group | Examples |
|-------|----------|
| Health | `GET /health`, `GET /v1/health`, `GET /health/detailed` |
| Chat | `POST /v1/chat/completions` |
| Hermes | `GET /v1/models`, `/v1/capabilities`, `/v1/runs`, `/api/sessions`, `/api/jobs` |
| Management | `GET/POST /api/holix/profiles`, `…/models`, `…/telegram`, `…/reload` |
| Admin | `POST /admin/api-keys`, `GET /admin/metrics`, `GET /metrics` (Prometheus) |

## Gateway API keys

Gateway API keys (`hx_…`) authenticate HTTP clients. There is **no** `holix` CLI command for creating them yet — use the admin API or Swagger UI.

**Bootstrap the first admin key** (one-time, when no keys exist):

```bash
export HOLIX_REQUIRE_AUTH=false
holix gateway start -f
# Create admin key (see below), save the returned hx_… value
# Then set HOLIX_REQUIRE_AUTH=true and restart
```

**Create keys** (requires an existing admin key):

```bash
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys?name=my-app&permissions=read,write&rate_limit=100" \
  -H "Authorization: Bearer hx_admin_…"
```

Or use Swagger at `/docs` → **Authorize** → paste your `hx_…` key → try `POST /admin/api-keys`.

Keys are shown **once** on create. Permissions: `read`, `write`, `execute`, `admin`. See [GATEWAY_API.md](GATEWAY_API.md) and [SECURITY.md](SECURITY.md).

**Profile access keys** (`hp_…`) are a separate layer for `/api/holix/*` — create via `holix profile key init`, not via `/admin/api-keys`.

## Interactive API docs

FastAPI serves OpenAPI documentation on the gateway port (default `8000`):

| URL | Format |
|-----|--------|
| `/docs` | Swagger UI — try endpoints in the browser |
| `/redoc` | ReDoc — readable reference |
| `/openapi.json` | Raw OpenAPI 3 schema |

Example: `http://127.0.0.1:8000/docs`

### Swagger Authorize

1. Open `/docs`
2. Click **Authorize** (lock icon)
3. Under **HolixApiKey**, paste your gateway API key (`hx_…`) — with or without the `Bearer ` prefix
4. **Authorize** → close the dialog
5. Protected endpoints now send `Authorization: Bearer hx_…` (also accepted as `X-API-Key`)

`/health` and `/v1/health` work without a key. All other routes require auth when `HOLIX_REQUIRE_AUTH=true`.

## Documentation site (`--with-docs`)

Bundle the Holix documentation site with the gateway:

```bash
holix gateway start --with-docs
# or: HOLIX_GATEWAY_WITH_DOCS=1 holix gateway start
```

Serves the built docs SPA on a companion port (default `8080`) alongside the API:

| Docs site | Content |
|-----------|---------|
| `http://127.0.0.1:8080/docs` | Documentation hub |
| `http://127.0.0.1:8080/docs/gateway-api` | **Full API reference** (every endpoint, curl examples) |
| `http://127.0.0.1:8000/docs` | **Swagger UI** on gateway port — try live requests |

Build content first with `holix docs build`. Optional docs-chat widget uses a **separate** token (`HOLIX_DOCS_CHAT_TOKEN`) — not the gateway `hx_` key. See [DEPLOYMENT.md](DEPLOYMENT.md#documentation-site-build-and-seo).

## Metrics

Two metrics surfaces — both require an **admin** API key:

| Endpoint | Format | Description |
|----------|--------|-------------|
| `GET /metrics` | Prometheus text | Root-level scrape target (common for Prometheus config) |
| `GET /admin/metrics` | JSON | In-memory counters and summary (`metrics`, `summary` fields) |
| `GET /admin/metrics/prometheus` | Prometheus text | Same Prometheus output as `/metrics` (hidden from OpenAPI schema) |

Disabled when `HOLIX_ENABLE_PROMETHEUS_METRICS=false` — `/metrics` and `/admin/metrics/prometheus` return 404; `/admin/metrics` JSON still works.