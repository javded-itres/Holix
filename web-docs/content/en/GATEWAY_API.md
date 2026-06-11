# Helix Gateway API — Complete Reference

> **On this documentation site:** `/docs/gateway-api` (same content as this page).  
> **Live OpenAPI (try requests):** `http://127.0.0.1:8000/docs` on the gateway port — not the docs site port.

Helix runs a **single multi-profile HTTP gateway** with three public surfaces:

| Surface | Prefix | Purpose |
|---------|--------|---------|
| **Hermes-compatible API** | `/v1`, `/api/sessions`, `/api/jobs` | Drop-in for Open WebUI, LobeChat, Hermes clients |
| **Helix agent extensions** | `/v1/chat/completions`, permissions, plans | OpenAI chat + tool permissions + plan review |
| **Helix Management API** | `/api/helix/` | SaaS control plane: profiles, models, MCP, skills, Telegram |

Operational guide (start/stop, ports, logs): [GATEWAY.md](GATEWAY.md).

### Hermes compatibility matrix

| Area | Status | Notes |
|------|--------|-------|
| `/v1/chat/completions`, `/v1/responses`, `/v1/runs` | Full | Bearer + `X-Hermes-*` header aliases |
| `/v1/models`, `/v1/capabilities`, `/v1/skills`, `/v1/toolsets` | Full | Capabilities advertises Hermes feature flags |
| `/api/sessions` CRUD + chat/stream | Full | `source`, `include_children`; persisted under `~/.helix/data/gateway/sessions.json` |
| `/api/jobs` CRUD + pause/resume/run | Full | Hermes body aliases: `prompt`, `schedule`, `delivery_target`, `skills`, `provider_override` |
| Multimodal inline images | Full | `image_url` / `input_image`; file uploads return `400 unsupported_content_type` |
| SSE tool progress | Full | `hermes.tool.progress`, `assistant.delta`, `tool.started`, `tool.completed`, `run.completed` |
| Job DELETE cancels in-flight run | Full | Shared cron active-run registry |
| Helix-only | Extra | `/api/helix/*`, permissions, plans — not in Hermes |

---

## Table of contents

1. [Base URL and interactive docs](#base-url-and-interactive-docs)
2. [Authentication](#authentication)
3. [Common concepts](#common-concepts)
4. [SaaS workflow examples](#saas-workflow-examples)
5. [Health & gateway info](#health--gateway-info)
6. [Admin API](#admin-api)
7. [Hermes API (`/v1`)](#hermes-api-v1)
8. [Agent extensions (`/v1`)](#agent-extensions-v1)
9. [Sessions (`/api/sessions`)](#sessions-apisessions)
10. [Cron jobs (`/api/jobs`)](#cron-jobs-apijobs)
11. [Management: profiles](#management-profiles)
12. [Management: models](#management-models)
13. [Management: skills](#management-skills)
14. [Management: MCP](#management-mcp)
15. [Management: config & env](#management-config--env)
16. [Management: global settings](#management-global-settings)
17. [Management: Telegram](#management-telegram)
18. [Docs-site chat API](#docs-site-chat-api)
19. [Multi-profile architecture](#multi-profile-architecture)
20. [Security notes](#security-notes)

---

## Base URL and interactive docs

Default base URL (per profile `.env`):

```text
http://127.0.0.1:8000
```

| Resource | URL | Auth |
|----------|-----|------|
| Swagger UI | `http://HOST:PORT/docs` | — |
| ReDoc | `http://HOST:PORT/redoc` | — |
| OpenAPI JSON | `http://HOST:PORT/openapi.json` | — |

### Swagger Authorize (one token for all requests)

1. Open `/docs`
2. Click **Authorize** (lock icon)
3. Under **HelixApiKey**, paste your gateway key (`hx_…`) **without** the `Bearer` prefix — Swagger adds it automatically
4. Try any protected endpoint with **Try it out**

`X-API-Key: hx_…` also works in curl and code but is not configured via the Authorize dialog.

Gateway metadata (requires API key):

```bash
curl -sS -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8000/
```

```json
{
  "name": "Helix API",
  "version": "0.2.0",
  "status": "running",
  "host_profile": "default",
  "loaded_profiles": ["default"],
  "require_auth": true
}
```

---

## Authentication

Helix uses up to **three independent auth mechanisms** depending on the route.

### Layer 1 — Gateway API key (`hx_…`)

Required on almost all routes when `HELIX_REQUIRE_AUTH=true` (default).

| Header | Example |
|--------|---------|
| `Authorization` | `Bearer hx_…` |
| `X-API-Key` | `hx_…` |

**Permissions** (comma-separated at creation): `read`, `write`, `execute`, `admin`. See [SECURITY.md](SECURITY.md).

**Create a key** — no CLI command yet; use HTTP or Swagger:

```bash
# Requires existing admin key, OR bootstrap with HELIX_REQUIRE_AUTH=false once
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -d "name=my-app&permissions=read,write,execute&rate_limit=100"
```

Response includes `api_key` — **shown once**. Store it securely.

**Bootstrap first admin key:**

```bash
helix profile env --edit   # HELIX_REQUIRE_AUTH=false
helix gateway reload
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys" \
  -d "name=admin&permissions=read,write,execute,admin&rate_limit=1000"
# Save hx_…, set HELIX_REQUIRE_AUTH=true, helix gateway reload
```

### Layer 2 — Profile access key (`hp_…`)

Required for `/api/helix/*` routes (in addition to gateway API key):

```http
X-Helix-Profile-Key: hp_…
```

| Caller | Headers | Scope |
|--------|---------|-------|
| Profile owner | Gateway key + `X-Helix-Profile-Key` for own profile | Single profile |
| Platform admin | Gateway key with `admin` permission **or** admin profile master key | All profiles |

Admin profile name defaults to `admin` (`HELIX_TELEGRAM_ADMIN_PROFILE`).

Profile keys are created via CLI (`helix profile key init`) or Management API (`POST …/key/init`). **Not** the same as `hx_…` gateway keys.

### Layer 3 — Docs-chat token (website widget only)

Routes under `/v1/docs/chat/*` (except `/config`) use `HELIX_DOCS_CHAT_TOKEN`:

| Header | Example |
|--------|---------|
| `Authorization` | `Bearer <docs-chat-token>` |
| `X-Docs-Chat-Token` | `<docs-chat-token>` |

Separate from gateway API keys. See [Docs-site chat API](#docs-site-chat-api).

### Public endpoints (no gateway API key)

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/v1/health` |
| GET | `/health/detailed` |
| GET | `/v1/docs/chat/config` |

---

## Common concepts

### Profile routing

For chat, Hermes, sessions, and jobs, profile is resolved in order:

1. `X-Helix-Profile` or `X-Hermes-Profile` header
2. `model` field in request body (profile name; not `helix`, `helix-agent`, `hermes-agent`)
3. Gateway **host profile** (`HELIX_PROFILE` at process start)

### Session headers (aliases)

| Purpose | Helix | Hermes alias |
|---------|-------|--------------|
| Conversation / transcript id | `X-Helix-Session-Id` | `X-Hermes-Session-Id` |
| Stable memory scope | `X-Helix-Session-Key` | `X-Hermes-Session-Key` |

Session key: max 256 chars; control characters rejected → `400`.

### `reload_required`

Management mutations that change running agent config return `"reload_required": true`. Apply without restarting uvicorn:

```bash
curl -sS -X POST "$HELIX_URL/api/helix/profiles/$PROFILE/reload" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Helix-Profile-Key: $PROFILE_KEY"
```

### Masked secrets

Management `GET` responses mask API keys, tokens, and sensitive env vars. Plaintext is returned **once** on create/init/rotate.

### Errors

| Code | Meaning |
|------|---------|
| 400 | Invalid body, headers, or business rule |
| 401 | Missing or invalid API key / profile key / docs-chat token |
| 403 | Valid key but insufficient permission |
| 404 | Resource not found or feature disabled |
| 409 | Conflict (e.g. profile exists, admin already assigned) |
| 429 | Per-key rate limit exceeded |
| 503 | Gateway not initialized (registry, key manager, agent) |

### Rate limiting

Each API key has `rate_limit` (requests per minute). Docs-chat has separate `HELIX_DOCS_CHAT_RATE_LIMIT_RPM` per `client_id`.

### Server-Sent Events (SSE)

Streaming endpoints return `text/event-stream`:

- `POST /v1/chat/completions` with `"stream": true`
- `GET /v1/runs/{id}/events`
- `POST /api/sessions/{id}/chat/stream`
- `POST /v1/docs/chat` with `"stream": true`

---

## SaaS workflow examples

```bash
export HELIX_URL=http://127.0.0.1:8000
export ADMIN_KEY=hx_…
export ADMIN_PROFILE_KEY=hp_…

# 1. Create tenant profile (admin)
curl -sS -X POST "$HELIX_URL/api/helix/profiles" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"tenant-42","with_access_key":true}'

# 2. Add LLM provider
curl -sS -X POST "$HELIX_URL/api/helix/profiles/tenant-42/models/providers" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "X-Helix-Profile-Key: $ADMIN_PROFILE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"preset_id":"openrouter","skip_test":true}'

# 3. Reload tenant agent + companions
curl -sS -X POST "$HELIX_URL/api/helix/profiles/tenant-42/reload" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "X-Helix-Profile-Key: $ADMIN_PROFILE_KEY"

# 4. Chat as tenant (OpenAI client: model = profile name)
curl -sS "$HELIX_URL/v1/chat/completions" \
  -H "Authorization: Bearer $TENANT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"tenant-42","messages":[{"role":"user","content":"hi"}]}'
```

More examples in each endpoint section below.

---

## Health & gateway info

### `GET /health`

**Auth:** Public

Basic liveness: `status`, `timestamp`, `agent_ready`, `require_auth`.

```bash
curl -sS http://127.0.0.1:8000/health
```

### `GET /v1/health`

**Auth:** Public

Minimal Hermes health: `{"status":"ok"}`.

### `GET /health/detailed`

**Auth:** Public (no API key)

Extended diagnostics: `host_profile`, `loaded_profiles`, `active_runs`, `companions` per profile, bind host/port.

```bash
curl -sS http://127.0.0.1:8000/health/detailed
```

### `GET /`

**Auth:** API key

Gateway version, host profile, loaded profiles. See [Base URL](#base-url-and-interactive-docs).

### `GET /metrics`

**Auth:** Admin API key

Prometheus text exposition (when `enable_prometheus_metrics=true`). Same format as admin prometheus endpoint.

```bash
curl -sS -H "Authorization: Bearer $ADMIN_KEY" http://127.0.0.1:8000/metrics
```

---

## Admin API

Prefix `/admin`. **Always** requires API key with `admin` permission.

### `POST /admin/api-keys`

Create a new gateway API key.

**Query parameters:**

| Param | Default | Description |
|-------|---------|-------------|
| `name` | required | Human-readable label |
| `permissions` | `read,write` | Comma-separated permissions |
| `rate_limit` | `100` | Requests per minute |

```bash
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys?name=ci&permissions=read,execute&rate_limit=200" \
  -H "Authorization: Bearer $ADMIN_KEY"
```

**Response:** `api_key` (once), `name`, `permissions`, `rate_limit`, `warning`.

### `GET /admin/api-keys`

List active keys (metadata only — no secret values).

### `DELETE /admin/api-keys/{key_id}`

Revoke key by numeric `id` from list response (path param name in OpenAPI: `key_id`; pass the key **id**, not the secret).

### `GET /admin/metrics`

JSON application metrics + summary.

### `GET /admin/metrics/prometheus`

Prometheus text (hidden from OpenAPI schema; same family as `GET /metrics`).

---

## Hermes API (`/v1`)

Hermes-compatible surface. All routes require gateway API key unless noted.

Profile headers apply where noted. See [Hermes agent docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md).

### `GET /v1/models`

List Helix profiles as OpenAI-style models (`id` = profile name).

```bash
curl -sS -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8000/v1/models
```

### `GET /v1/capabilities`

Feature flags and endpoint map for Hermes clients.

### `GET /v1/toolsets`

Agent tools grouped as a single `"core"` toolset for the resolved profile.

### `GET /v1/skills`

Skills list: `[{name, description, category}]`.

### `POST /v1/responses`

Create a stored response (Responses API). Requires `read` permission.

**Body (`ResponsesCreateRequest`):**

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Profile name (default `helix`) |
| `input` | string or array | User input |
| `instructions` | string? | System instructions |
| `store` | bool | Persist in SQLite store (default true) |
| `previous_response_id` | string? | Chain responses |
| `conversation` | string? | Conversation id |

### `GET /v1/responses/{response_id}`

Retrieve stored response.

### `DELETE /v1/responses/{response_id}`

Delete stored response.

### `POST /v1/runs`

Submit async agent run. Requires `execute` or `read`.

**Body (`RunsCreateRequest`):** `model`, `input`, `session_id`, `instructions`, `conversation_history`, `previous_response_id`.

### `GET /v1/runs/{run_id}`

Poll run status and output.

### `GET /v1/runs/{run_id}/events`

SSE stream of run events until completion.

### `POST /v1/runs/{run_id}/stop`

Request cancellation.

### `POST /v1/runs/{run_id}/approval`

Human-in-the-loop approval.

**Body:** `{"decision":"approve"|"reject", "comment": "…"}`

---

## Agent extensions (`/v1`)

Helix-specific agent endpoints (OpenAI chat, permissions, plans).

### `POST /v1/chat/completions`

OpenAI-compatible chat. Requires `read` on API key.

**Body:** standard `ChatCompletionRequest` — `model`, `messages`, optional `stream`, `conversation_id`.

```bash
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

With streaming: `"stream": true` → SSE chunks.

### `GET /v1/conversations/{conversation_id}`

Conversation history. Query: `limit` (default 30).

### `GET /v1/tools`

List tools available to the agent for the resolved profile.

### `POST /v1/search`

Memory search. Query params: `query`, `top_k`.

### `POST /v1/permissions/grant`

Grant tool permission. Requires `execute`. Params: `tool_name`, `risk_level`, `scope` (`session`|`permanent`).

### `GET /v1/permissions`

List current permission grants.

### `DELETE /v1/permissions/{grant_key}`

Revoke grant. Query: `scope`.

### `POST /v1/confirmations/resolve`

Resolve risky-action confirmation from agent UI flow.

### `POST /v1/plan/review`

Resolve plan review: `review_id`, `choice`, `feedback`.

### `GET /v1/plans`

List plans. Query: `limit` (default 20).

### `GET /v1/plans/{plan_id}`

Get plan by id.

---

## Sessions (`/api/sessions`)

Hermes session store per profile.

### `GET /api/sessions`

List sessions. Query: `limit` (50), `offset` (0). Profile via `X-Helix-Profile`.

### `POST /api/sessions`

Create session. Body: `{"title":"","profile":null}`.

### `GET /api/sessions/{session_id}`

Get session metadata.

### `PATCH /api/sessions/{session_id}`

Update `title`, `end_reason`.

### `DELETE /api/sessions/{session_id}`

Delete session.

### `GET /api/sessions/{session_id}/messages`

Messages for session. Query: `limit` (50).

### `POST /api/sessions/{session_id}/fork`

Fork session to new id.

### `POST /api/sessions/{session_id}/chat`

Chat in session context. Body: `{"input":"…","model":null}`. Requires `read`.

### `POST /api/sessions/{session_id}/chat/stream`

Same as chat but SSE stream.

---

## Cron jobs (`/api/jobs`)

Per-profile scheduled tasks (gateway cron companion).

### `GET /api/jobs`

List cron jobs for resolved profile.

### `POST /api/jobs`

Create job.

**Body (`JobCreateRequest`):**

| Field | Hermes alias | Description |
|-------|--------------|-------------|
| `task` | `prompt` | Natural-language instruction for agent |
| `cron_expression` | `schedule` | 5-field cron or phrases (`every day at 9`, `hourly`) |
| `name` | — | Display name |
| `enabled` | — | Active flag |
| `notify_chat_id` | `delivery_target` | Telegram chat for notifications |
| `session_id` | — | Session that receives run summaries |
| `skills` | — | Preferred skills list for the run |
| `model_override` | `provider_override` | Optional model override for this job |

```bash
curl -sS -X POST http://127.0.0.1:8000/api/jobs \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"task":"Daily summary","cron_expression":"0 9 * * *","name":"morning"}'
```

### `GET /api/jobs/{job_id}`

Get job details.

### `PATCH /api/jobs/{job_id}`

Update any of: `task`, `cron_expression`, `name`, `enabled`, `notify_chat_id`, `session_id`.

### `DELETE /api/jobs/{job_id}`

Remove job and cancel any in-flight run.

### `POST /api/jobs/{job_id}/pause`

Disable job (`enabled=false`).

### `POST /api/jobs/{job_id}/resume`

Enable job.

### `POST /api/jobs/{job_id}/run`

Run job immediately (one-shot).

---

## Management: profiles

Prefix `/api/helix/profiles`. Gateway API key + profile access (see [Authentication](#authentication)).

### `GET /api/helix/profiles`

**Auth:** Admin

List all profiles with `name`, `protected`, `path`.

### `POST /api/helix/profiles`

**Auth:** Admin

Create profile.

**Body (`ProfileCreateRequest`):**

| Field | Default | Description |
|-------|---------|-------------|
| `name` | required | Profile id |
| `inherit_global` | true | Copy global config |
| `with_access_key` | false | Generate `hp_…` access key |
| `workspace_jail` | false | Enable workspace isolation |

**Response:** `profile`, `access_key` (if created), `protected`, `reload_required`.

### `GET /api/helix/profiles/{profile_id}`

Profile metadata: jail settings, paths.

### `GET /api/helix/profiles/{profile_id}/status`

Agent loaded in registry, companion status (Telegram, cron).

### `DELETE /api/helix/profiles/{profile_id}`

**Auth:** Admin. Delete profile directory.

### `POST /api/helix/profiles/{profile_id}/reload`

Reload agent + Telegram + cron for this profile.

### `GET /api/helix/profiles/{profile_id}/key/status`

Whether profile requires access key.

### `POST /api/helix/profiles/{profile_id}/key/init`

Enable access key + workspace jail. Returns new `hp_…` once.

### `POST /api/helix/profiles/{profile_id}/key/rotate`

**Body:** `{"current_key":"hp_…"}`. Returns new key once.

### `POST /api/helix/profiles/{profile_id}/key/disable`

**Auth:** Admin. Remove access key protection.

### `GET /api/helix/profiles/{profile_id}/jail`

Workspace jail enabled/path.

### `POST /api/helix/profiles/{profile_id}/jail/enable`

**Body:** optional `{"path":"/allowed/root"}`.

### `POST /api/helix/profiles/{profile_id}/jail/disable`

Disable workspace jail.

---

## Management: models

Prefix `/api/helix/profiles/{profile_id}/models`.

### `GET …/presets`

Provider catalog (OpenRouter, Ollama, etc.).

### `GET …/providers`

Configured providers (API keys masked).

### `POST …/providers`

Add provider from preset.

**Body (`ProviderAddRequest`):** `preset_id`, optional `name`, `api_key`, `host`, `port`, `skip_test`, `no_verify_ssl`.

### `DELETE …/providers/{provider_name}`

Remove provider from profile config.

### `POST …/providers/{provider_name}/test`

Probe connectivity and discover models.

### `GET …/agent-models`

Map of agent role → model configuration.

### `PATCH …/agent-models`

**Body:** `{"agent_models":{…}}`.

### `GET …/fallbacks`

Ordered fallback provider chain.

### `PATCH …/fallbacks`

**Body:** `{"providers":["openrouter","ollama"]}`.

---

## Management: skills

Prefix `/api/helix/profiles/{profile_id}/skills`.

### `GET …/skills`

List skills. Query: `limit`, `agent` (filter by assignment).

### `GET …/skills/search`

Semantic search. Query: `q` (required).

### `GET …/skills/{skill_name}`

Skill metadata and markdown content.

### `GET …/skills/assignments`

Skill → agent allowlists.

### `PATCH …/skills/assignments`

**Body:** `{"assignments":{"agent_name":["skill-a","skill-b"]}}`.

### `POST …/skills/seed-bundled`

Install bundled skills. Query: `force` (bool).

---

## Management: MCP

Prefix `/api/helix/profiles/{profile_id}/mcp`.

### `GET …/servers`

All MCP servers + assignments.

### `POST …/servers`

**Body (`McpServerCreateRequest`):** `name`, `transport` (`stdio`|`sse`), `command`, `args`, `url`, `env`, `risk_level`.

### `GET …/servers/{server_name}`

Single server config (masked).

### `DELETE …/servers/{server_name}`

Remove server.

### `POST …/servers/{server_name}/test`

Connect and list remote tools.

### `GET …/assignments`

Agent → MCP server mapping.

### `PATCH …/assignments`

**Body:** `{"assignments":{"agent":["server-a"]}}`.

### `GET …/popular`

Curated installable MCP servers.

### `POST …/install`

**Body (`McpInstallRequest`):** `popular_key` or `git_url`, optional `params`.

---

## Management: config & env

Prefix `/api/helix/profiles/{profile_id}`.

### `GET …/config`

Profile `config.yaml` (secrets masked).

### `PATCH …/config`

**Body:** `{"updates":{…}}` deep-merged into profile config. Returns `reload_required`.

### `GET …/env`

Profile `.env` variables (masked).

### `PATCH …/env`

**Body:** `{"variables":{"KEY":"value"}}`.

---

## Management: global settings

Prefix `/api/helix/global`. **Admin** profile access required.

### `POST /api/helix/global/init`

Create `~/.helix/global/config.yaml` and `.env` templates.

### `GET /api/helix/global/config`

Read global config (masked).

### `PATCH /api/helix/global/config`

Patch global YAML.

### `GET /api/helix/global/env`

Read global `.env` (masked).

### `PATCH /api/helix/global/env`

Patch global environment variables.

---

## Management: Telegram

Prefix `/api/helix/profiles/{profile_id}/telegram`. CLI equivalents in [TELEGRAM.md](TELEGRAM.md).

### `GET …/status`

Bot configured, token masked, pending access requests, user map, companions.

### `POST …/setup`

**Body:** `{"bot_token":"…","also_project_env":false}`. Verifies via Telegram `getMe`, saves `telegram.env`.

### `GET …/requests`

Pending access requests list + count.

### `POST …/requests/{user_id}/approve`

**Auth:** Admin profile access.

**Body (`TelegramApproveRequest`):** one of `profile`, `create_profile`, or `set_admin:true`.

### `POST …/requests/{user_id}/reject`

**Auth:** Admin. Reject pending request.

### `GET …/admin`

Telegram admin user id and mapped Helix profile.

### `DELETE …/admin`

**Auth:** Admin. Clear Telegram admin.

### `GET …/map`

User id → Helix profile mapping.

### `POST …/map`

**Body:** `{"user_id":12345,"profile":"alice"}`.

### `DELETE …/map/{user_id}`

Remove mapping.

### `POST …/sync-menu`

Push bot command menu to Telegram API.

---

## Docs-site chat API

Prefix `/v1/docs/chat`. Powers the documentation website widget — **no agent tools**, RAG over docs only.

### `GET /v1/docs/chat/config`

**Auth:** Public

`{"enabled":true,"proxy_path":"/api/docs-chat",…}`

### `GET /v1/docs/chat/session`

**Auth:** Docs-chat token

Query: `client_id` (8–64 chars). Returns saved visitor chat history.

### `DELETE /v1/docs/chat/session`

**Auth:** Docs-chat token

Clear history for `client_id`.

### `POST /v1/docs/chat`

**Auth:** Docs-chat token

**Body:**

| Field | Description |
|-------|-------------|
| `message` | Question (1–4000 chars) |
| `client_id` | Anonymous visitor id |
| `lang` | `en` or `ru` |
| `page_slug` | Optional current doc page |
| `stream` | SSE if true (default) |

Rate limited per `client_id` (`HELIX_DOCS_CHAT_RATE_LIMIT_RPM`).

---

## Multi-profile architecture

One uvicorn process serves **N profiles** via `ProfileAgentRegistry`:

- Agents lazy-load on first request
- `CompanionManager` runs Telegram polling + cron per profile
- `POST …/reload` restarts one profile's agent and companions without gateway restart
- Host profile set at startup (`HELIX_PROFILE`)

Stores: `ResponsesStore` (SQLite), `RunsStore` (memory), `SessionsStore` (memory).

---

## Security notes

- Use **TLS** behind reverse proxy in production; bind `127.0.0.1` by default
- Set `HELIX_API_KEY_PEPPER` in production (required when `HELIX_ENV=production`)
- Admin routes always require admin permission
- Security headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`
- CORS: `HELIX_CORS_ORIGINS` (comma-separated)

See also: [SECURITY.md](SECURITY.md), [DEPLOYMENT.md](DEPLOYMENT.md), [PROFILES.md](PROFILES.md), [TELEGRAM.md](TELEGRAM.md).