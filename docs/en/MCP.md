# Model Context Protocol (MCP)

Holix connects external **MCP servers** (stdio or SSE) and exposes their tools to the agent as `mcp_<server>_<tool>`.

Configuration is **per profile** in `config.yaml`: `mcp_servers` and `mcp_assignments`.

---

## Prerequisites

- **Node.js** and `npx` for many community servers — `holix doctor` checks PATH
- Optional: **Docker** for containerized MCP servers (e.g. GitHub)

---

## Quick setup

```bash
holix mcp setup              # add servers + assign to agents
holix mcp list-popular       # curated list
holix mcp install filesystem # from popular list
holix mcp test my-server     # connect and list tools
holix doctor                 # verify env placeholders
```

In TUI/Telegram: `/mcp`, `/mcp install`, `/mcp assign` — [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

CLI reference: [CLI.md](CLI.md#mcp).

---

## Configuration (`config.yaml`)

```yaml
mcp_servers:
  filesystem:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"]
  my-sse:
    transport: sse
    url: http://127.0.0.1:3001/sse

mcp_assignments:
  main: [filesystem]
  coder: [filesystem, my-sse]
```

| Field | Meaning |
|-------|---------|
| `mcp_servers` | Server definitions (name → transport, command/args or URL) |
| `mcp_assignments` | Which agents (`main`, `coder`, sub-agent slots) receive which servers |

Tools appear at runtime as **`mcp_<server>_<toolname>`** (server name normalized).

Edit via wizard:

```bash
holix mcp add
holix mcp assign
```

Or `holix config edit` / `holix profile global edit` for shared defaults.

---

## Assignments and agents

| Agent slot | Typical use |
|------------|-------------|
| `main` | Default chat agent |
| `coder`, `researcher`, … | Sub-agent types — see [SUBAGENTS.md](SUBAGENTS.md) |
| Custom types | From `/subagent-types` — assign MCP per type |

Only servers listed in `mcp_assignments` for the active agent are loaded.

---

## Install from git or custom command

```bash
holix mcp install https://github.com/org/my-mcp-server
holix mcp add my-custom   # manual stdio/SSE wizard
```

After install, run `holix mcp test <name>` before relying on tools in chat.

---

## Gateway management API

When the gateway runs, profile MCP can be managed over HTTP:

`GET/POST /api/holix/profiles/{id}/mcp` — see [GATEWAY_API.md](GATEWAY_API.md).

---

## Troubleshooting

| Problem | Action |
|---------|--------|
| Tools missing in chat | `holix mcp list`; check `mcp_assignments` for active agent |
| `npx` not found | Install Node.js; `holix doctor --fix` |
| Server fails to start | `holix mcp test <name>`; check command path and env in server config |
| Placeholder env vars | `holix doctor` — fill secrets in profile `.env` |

---

## See also

- [HUB.md](HUB.md) — skill catalogs (separate from MCP)
- [CONFIGURATION.md](CONFIGURATION.md) — global vs profile config layers
- [ARCHITECTURE.md](ARCHITECTURE.md) — `core/mcp/`