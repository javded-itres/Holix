# Build an App Without Importing Holix

Use this path when your application is **not** a Python package embedded in Holix — e.g. mobile app, Electron UI, SaaS dashboard, or separate backend in another language.

## Architecture

```
[Your App]  ──HTTP/SSE/MCP──►  [Holix Gateway :8000]
```

Holix Gateway exposes stable HTTP surfaces. Your app never imports `Holix` or `holix_sdk`.

## 1. Start the gateway

```bash
holix gateway start
# Default: http://127.0.0.1:8000
```

Create an API key via admin API or profile config. See [GATEWAY.md](GATEWAY.md).

## 2. Choose an API surface

| Surface | Prefix | Best for |
|---------|--------|----------|
| Hermes-compatible | `/v1`, `/api/sessions` | Chat UIs (Open WebUI, LobeChat, custom clients) |
| OpenAI-style legacy | `/v1/chat/completions` | Existing OpenAI SDK clients |
| Holix management | `/api/holix/` | Profile/model/MCP/skills admin |
| Extension routes | `/studio`, … | Optional host extensions when enabled |

Full reference: [GATEWAY_API.md](GATEWAY_API.md).

## 3. Chat with streaming (SSE)

```bash
curl -N -H "Authorization: Bearer hx_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"default","messages":[{"role":"user","content":"Hello"}],"stream":true}' \
  http://127.0.0.1:8000/v1/chat/completions
```

Hermes events include `assistant.delta`, `tool.started`, `tool.completed`, `run.completed`.

## 4. Sessions API

```bash
# Create session
curl -X POST -H "Authorization: Bearer hx_YOUR_KEY" \
  http://127.0.0.1:8000/api/sessions

# Stream chat in session
curl -N -H "Authorization: Bearer hx_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain this repo"}' \
  http://127.0.0.1:8000/api/sessions/SESSION_ID/chat/stream
```

## 5. MCP instead of HTTP

Configure MCP servers in the Holix profile. Your app can be an MCP **client** that talks to Holix-exposed tools, or run its own MCP server that Holix connects to.

See [MCP.md](MCP.md).

## 6. OpenAPI

Interactive docs on the running gateway:

- Swagger: `http://HOST:PORT/docs`
- OpenAPI JSON: `http://HOST:PORT/openapi.json`

## 7. Studio as API-only client

Holix Studio can run as a sidecar (`holix studio serve`) and talk to a remote gateway. Enable Studio routes on gateway with `HOLIX_STUDIO_ENABLED=1`.

## Security checklist

- Use HTTPS in production (reverse proxy)
- Scope API keys per profile
- Do not expose gateway on `0.0.0.0` without auth
- See [SECURITY.md](SECURITY.md) and [DEPLOYMENT.md](DEPLOYMENT.md)

## When to use holix-sdk instead

If you write a **Python package** installed alongside Holix (CLI subtree, gateway routes, agent tools), use [EXTENSIONS.md](EXTENSIONS.md) and import `holix_sdk` only.