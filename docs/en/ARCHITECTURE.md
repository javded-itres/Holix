# Architecture

Helix is a Python agent platform with a single execution path for reasoning, event-driven observability, and pluggable tools/skills/MCP.

## Execution flow

```
HelixAgent (core/agent.py)
    → run_agent_loop() / LangGraph (core/agent_execution.py)
    → yields AgentEvent (core/agent_events.py)
    → ToolRegistry, MemoryManager, SkillManager
```

| Adapter | Role |
|---------|------|
| `AgentLoop` | Collects events into final string (CLI chat) |
| `StreamingAgentLoop` | SSE for API gateway |
| TUI host | Subscribes to events, slash commands, confirmations |

## Component map

| Component | Path | Role |
|-----------|------|------|
| Agent | `core/agent.py` | Orchestrates memory, skills, tools, loop |
| Execution | `core/agent_execution.py` | Unified agent loop |
| Events | `core/agent_events.py` | Pub/sub `AgentEventBus` |
| Tools | `core/tools/` | `BaseTool`, registry, browser, terminal |
| Memory | `core/memory/` | SQLite + ChromaDB |
| Skills | `core/skills/` | Markdown skills, generator, hub |
| Models | `core/models/` | Multi-provider routing |
| MCP | `core/mcp/` | MCP client and tool prefixing |
| Hub | `core/hub/` | Catalog install, slash registry |
| Security | `core/security/` | Auth, permissions, confirmations |
| DI | `core/di/` | Dishka, `HelixRuntimeConfig` |
| API | `api/gateway.py` | FastAPI, OpenAI-compatible `/v1/chat/completions` |
| CLI | `cli/main.py` | Typer entry |
| Gateway supervisor | `cli/services/supervisor.py` | Background `gateway start` |
| Doctor | `cli/doctor/` | Diagnostics |
| TUI | `cli/tui/code/` | Textual UI |
| Shared slash | `cli/shared/commands/` | TUI + Telegram `/` commands |

## Configuration

1. **`.env`** — global `Settings` (`config.py`)
2. **Profile** — `~/.helix/profiles/<name>/config.yaml`
3. **CLI flags** — per-command overrides

Project dir may supplement `./.helix/skills`, `.helix/plan`, local MCP — merged, not replacing profile system keys.

## Extension points

- **Events** — subscribe to `AgentEventBus` for UI, logging, metrics without changing the loop
- **Tools** — subclass `BaseTool`, register in `core/tools/registry.py`
- **Skills** — markdown under `data/skills/`; hub bundles under `data/skills/_hub/`
- **MCP** — `mcp_<server>_<tool>` naming in profile config

## Interfaces

| Interface | Entry |
|-----------|--------|
| TUI | `helix tui` |
| Chat REPL | `helix chat-command` |
| One-shot | `helix run` |
| HTTP | `helix gateway start` → FastAPI |
| Telegram | `helix telegram run` or gateway companion |

## See also

- [CLI.md](CLI.md)
- [GATEWAY.md](GATEWAY.md)
- [SECURITY.md](SECURITY.md)