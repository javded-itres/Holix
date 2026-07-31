# Agent2Agent (A2A) protocol

Holix can participate in the open **[Agent2Agent (A2A)](https://a2a-protocol.org)** ecosystem:

| Role | What Holix does |
|------|-----------------|
| **A2A Server** | Exposes the profile agent via gateway: Agent Card + JSON-RPC / REST + **SSE streaming** |
| **A2A Client** | Tools to discover remote agents and send them tasks |

Internal Holix **sub-agents** stay process-local. A2A is for **interop with other systems** (other frameworks, vendors, gateways).

## Enable / configure

Profile `config.yaml` (or env):

```yaml
a2a:
  enabled: true
  # Optional public URL advertised in the Agent Card
  public_url: https://agent.example.com/a2a
  name: Holix Coding Agent
  description: Workspace agent with skills, MCP, SDD
  request_timeout_s: 300
  # Remotes Holix may call as a client
  remote_agents:
    - name: research
      url: https://other.example.com/a2a
      description: Research specialist
      headers:
        Authorization: Bearer ${REMOTE_A2A_TOKEN}
```

Environment overrides:

| Variable | Meaning |
|----------|---------|
| `HOLIX_A2A_ENABLED` | `true` / `false` (default on) |
| `HOLIX_A2A_PUBLIC_URL` | Public base URL for the Agent Card |
| `HOLIX_A2A_TIMEOUT_S` | Client timeout seconds |

## Server endpoints (gateway)

Requires a Holix gateway API key (`hx_…`) like other `/v1` routes.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/.well-known/agent.json` | Agent Card discovery |
| `GET` | `/a2a/.well-known/agent.json` | Same under `/a2a` |
| `POST` | `/a2a` | JSON-RPC 2.0 (send, **stream**, tasks, card) |
| `POST` | `/a2a/message:send` | REST send (JSON or SSE if `Accept: text/event-stream`) |
| `POST` | `/a2a/message:stream` | REST send — always SSE |
| `GET` | `/a2a/tasks/{id}` | REST get task |
| `GET` | `/a2a/tasks/{id}/subscribe` | SSE snapshot of task state |

Optional headers: `X-Holix-Profile` (multi-profile gateway).

Agent Card advertises:

```json
"capabilities": {
  "streaming": true,
  "pushNotifications": false
}
```

### JSON-RPC — blocking send

```bash
curl -sS -X POST "http://127.0.0.1:8000/a2a" \
  -H "Authorization: Bearer $HOLIX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Summarize the workspace README"}]
      },
      "configuration": {"returnImmediately": false}
    }
  }'
```

`contextId` on the message is mapped to a Holix conversation (`a2a:<contextId>`) for multi-turn.

### JSON-RPC — streaming (SSE)

```bash
curl -sSN -X POST "http://127.0.0.1:8000/a2a" \
  -H "Authorization: Bearer $HOLIX_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": "stream-1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Write a short haiku about code"}]
      }
    }
  }'
```

Each SSE event is a JSON-RPC response with a StreamResponse `result`:

```
data: {"jsonrpc":"2.0","id":"stream-1","result":{"task":{...}}}

data: {"jsonrpc":"2.0","id":"stream-1","result":{"statusUpdate":{"taskId":"...","status":{"state":"working"},"final":false}}}

data: {"jsonrpc":"2.0","id":"stream-1","result":{"artifactUpdate":{"taskId":"...","artifact":{...},"append":true}}}

data: {"jsonrpc":"2.0","id":"stream-1","result":{"statusUpdate":{"status":{"state":"completed"},"final":true}}}
```

Aliases for the stream method: `message/stream`, `message/sendStreamingMessage`, `message/sendSubscribe`.

You can also call `message/send` with `Accept: text/event-stream` to force SSE.

### REST streaming

```bash
curl -sSN -X POST "http://127.0.0.1:8000/a2a/message:stream" \
  -H "Authorization: Bearer $HOLIX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "Hello from A2A REST stream"}]
    }
  }'
```

SSE payloads are bare StreamResponse objects (`{"task":…}`, `{"statusUpdate":…}`, `{"artifactUpdate":…}`) without a JSON-RPC envelope.

## Client tools (Holix agent)

When A2A is enabled, the agent gets:

| Tool | Role |
|------|------|
| `a2a_list_agents` | Configured remotes |
| `a2a_discover` | Fetch remote Agent Card |
| `a2a_send_message` | Send a task and wait for completion (blocking) |
| `a2a_get_task` | Poll a remote task id |

Example skill-style usage:

1. `a2a_list_agents` → pick `research`
2. `a2a_discover(agent="research")` → check skills / `capabilities.streaming`
3. `a2a_send_message(agent="research", message="…")` → use returned `text`

## Relation to MCP and sub-agents

| Mechanism | Scope |
|-----------|--------|
| **MCP** | Tools/resources from servers |
| **Sub-agents** | Holix-internal specialized workers |
| **A2A** | Opaque remote agents over HTTP (standard protocol) |

## Streaming behaviour (implementation notes)

- Holix runs the agent with `run_holix(..., stream=True)` and maps events:
  - thinking / tool start-result → `statusUpdate` (`working`)
  - assistant token deltas → `artifactUpdate` (append chunks)
  - final answer → completed `statusUpdate` (`final: true`) + full artifact
- Task store is process-local (gateway lifetime); subscribe on an old task returns a snapshot, not live mid-run progress (use `message/stream` for live runs).
- Push notifications remain off in the Agent Card (webhook delivery not implemented).

## Spec

- https://a2a-protocol.org  
- Protocol versions referenced: **0.3** / **1.0** (JSON-RPC + REST + Agent Card + SSE)
