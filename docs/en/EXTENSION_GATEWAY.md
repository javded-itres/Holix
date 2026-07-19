# Holix Extension Gateway Contract

Public HTTP contract for **external applications** and **host extensions** integrating with Holix Gateway.

## Base URL

```text
http://127.0.0.1:8000   # default per profile .env
```

## Authentication

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer hx_…` |
| `X-API-Key` | `hx_…` (curl/scripts) |

Hermes clients may also use `X-Hermes-API-Key` aliases — see [GATEWAY_API.md](GATEWAY_API.md).

## Extension mount points

Host extensions register routes via `holix.extensions` → `mount_gateway(app)`.

Built-in extensions:

| Extension | Prefix | Env gate |
|-----------|--------|----------|
| `telegram` | `/api/holix/profiles/{id}/telegram` | profile config |
| `max` | `/api/holix/profiles/{id}/max` + webhook | `MAX_WEBHOOK_*` |
| `studio` | `/studio` | `HOLIX_STUDIO_ENABLED=1` |

Third-party extensions choose their own prefix (e.g. `/analytics`).

## Core surfaces (always available)

| Surface | Paths | Purpose |
|---------|-------|---------|
| Health | `GET /health`, `/v1/health` | Liveness |
| Hermes | `/v1/*`, `/api/sessions`, `/api/jobs` | Chat, sessions, cron |
| Management | `/api/holix/*` | Profiles, models, skills, MCP |
| Admin | `/admin/*` | API keys, metrics |

## SSE event types (Hermes stream)

| Event | Payload |
|-------|---------|
| `assistant.delta` | `{ "delta": "…" }` |
| `tool.started` | `{ "name", "arguments" }` |
| `tool.completed` | `{ "name", "result" }` |
| `hermes.tool.progress` | Tool progress updates |
| `run.completed` | Final run metadata |

## Permissions model

Extensions declare `permissions` in code or `holix.plugin.json`:

- `gateway` — required to call `mount_gateway()`
- `network` — messengers, outbound HTTP sidecars
- `filesystem` — workspace file APIs
- `tools` — agent tool registration (agent extensions)

Holix logs a warning and skips mount/register when permissions are insufficient.

## OpenAPI

- Live schema: `GET /openapi.json`
- Swagger UI: `GET /docs`

Version field on FastAPI app reflects gateway release (see `api/gateway.py`).

## Related docs

- [GATEWAY_API.md](GATEWAY_API.md) — full endpoint reference
- [BUILD_WITHOUT_HOLIX.md](BUILD_WITHOUT_HOLIX.md) — external app guide
- [EXTENSIONS.md](EXTENSIONS.md) — Python extension SDK (`holix-sdk`)