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

Only servers listed in `mcp_assignments` for the active agent are loaded when that allow-list exists. With no list, every configured server is available.

## Workspace overlay

Ask the agent to connect a server and it writes `<workspace>/.holix/config.yaml` (`workspace_holix`). The agent cannot read `~/.holix/profiles`.

Paste a link in the chat and the agent installs it there. A GitHub or GitLab repository with `SKILL.md` (or a `skills.sh` / ClawHub / raw `SKILL.md` link) becomes a workspace skill. A repository whose name contains `mcp`, or any repo with an MCP entrypoint and no `SKILL.md`, becomes a stdio server. An `https://…/mcp` URL is bridged with `mcp-remote`. An `https://…/sse` URL stays on the SSE client.

```yaml
mcp_servers:
  context7:
    transport: stdio
    command: npx
    args: ["-y", "@upstash/context7-mcp"]
```

A server name already in the profile is replaced by this file. A new name is added, and if `main` has an allow-list the new name is appended there. A `mcp_assignments` block in the same file replaces that slot's list. Model, providers, and auth in this file are ignored. A changed command for a server that is already connected applies after a gateway restart.

---

## Remote HTTP (`mcp-remote`)

Holix's client speaks stdio and the older SSE transport. A Streamable HTTP server is added as `transport: http`. At start Holix runs `npx -y mcp-remote <url>`, which is a stdio process that speaks HTTP first and falls back to SSE.

```yaml
mcp_servers:
  docs:
    transport: http
    url: https://example.com/mcp
    headers:
      Authorization: "Bearer ${DOCS_TOKEN}"
```

An `http://` URL also passes `--allow-http` (private network or loopback). Header values are given to `mcp-remote` as `--header Name:${ENV}` so the secret is not put on the command line. `holix mcp list` still shows the URL, not the bridge command.

## Install from git or custom command

```bash
holix mcp install https://github.com/org/my-mcp-server
holix mcp add my-custom   # manual stdio/SSE wizard
holix mcp add docs --transport http --url https://example.com/mcp
holix mcp add docs --transport http --url http://127.0.0.1:4000/mcp --header "Authorization: Bearer $TOKEN"
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
