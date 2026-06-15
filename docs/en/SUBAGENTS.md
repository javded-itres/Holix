# Holix sub-agents

Background workers that run **specialized tasks** without blocking the main chat. Holix ships **predefined sub-agent types** (researcher, coder, …); you **spawn** them on a task — you do not create new types through the UI.

## Enable sub-agents

In the profile `config.yaml` or global `.env`:

```yaml
enable_subagents: true
subagent_default_process_mode: process   # process | async
subagent_max_concurrent: 4
subagent_process_timeout: 120
```

Default in Holix: `enable_subagents: true`.

If disabled, `delegate_to_subagent` and `/subagent-spawn` return an error.

---

## Built-in types

| Type | Role | Main tools |
|------|------|------------|
| `researcher` | Deep research, files, web | `web_search`, `web_fetch`, `read_file`, `list_directory` |
| `web_researcher` | Web search + synthesis | `web_search`, `web_fetch` |
| `coder` | Write, edit, debug code | `read_file`, `write_file`, `terminal`, `code_executor` |
| `analyst` | Data / SQL analysis | `sql_query`, `sql_schema`, `code_executor`, `math_calculator` |
| `reviewer` | Code review | `read_file`, `list_directory`, `terminal` |
| `writer` | Docs and content | `read_file`, `write_file`, `list_directory` |

Built-in definitions live in `core/subagents/registry.py` (`PREDEFINED_SUBAGENTS`).

---

## Create a new sub-agent type

Holix distinguishes **type** (role, prompt, tools) from **instance** (a running worker).

### TUI (recommended)

In `holix tui`:

```text
/subagent-types
```

Opens a manager where you can:

| Field | Purpose |
|-------|---------|
| **Name** | Unique slug (`security-auditor`) — not `coder`, `researcher`, … |
| **System prompt** | Role and behavior rules |
| **Tools** | Holix tools (`read_file`, `terminal`, `web_search`, …) |
| **Skills** | Profile skills allowlist for this type (`skill_assignments`) |
| **MCP** | MCP servers from profile `mcp_servers` |
| **Model slot** | Use a preset from `agent_models`, or inherit parent model |
| **External CLI** | Assign `holix launch` CLI (Claude Code, OpenCode, …) |

Saved per profile in:

`~/.holix/profiles/<profile>/subagents/types.json`

On save, Holix also updates `skill_assignments`, `mcp_assignments`, external CLI bindings, and optional `agent_models` for the chosen slot.

List types in chat:

```text
/subagent-types list
```

Then spawn:

```text
/subagent-spawn security-auditor Scan auth module for OWASP issues
```

### Code (built-in or fork)

To ship a **built-in** type with Holix, add an entry to `PREDEFINED_SUBAGENTS` in `core/subagents/registry.py` (name, `system_prompt`, `tools`, `max_steps`). Restart Holix after editing the repo.

---

## Spawn a sub-agent (create a run)

“Creating” a sub-agent means **starting a worker** of a given type with a task.

### TUI slash commands

```text
/subagent-spawn coder Fix failing tests in tests/
/subagents
/subagent-result coder
/subagent-terminate coder
```

| Command | Action |
|---------|--------|
| `/subagents` | List running and recent jobs |
| `/subagent-spawn <type> <task>` | Start background worker |
| `/subagent-result <job_id>` | Show completed response |
| `/subagent-terminate <job_id>` | Cancel a running job |
| `/subagent-reply <job_id> <text>` | Answer a sub-agent question (when it used `ask_user`) |

If `coder` is already running, Holix allocates `coder-2`, `coder-3`, …

### Main agent (automatic)

Ask in chat, for example:

```text
Run researcher in the background: gather API docs for our auth module
```

The main agent calls `delegate_to_subagent(agent_type, task)`, gets a `job_id`, and may use `wait_subagent_result(job_id)` when the answer is needed.

Available tools on the main agent (when `enable_subagents: true`):

- `delegate_to_subagent`
- `wait_subagent_result`
- `list_subagents`
- `terminate_subagent`

### Plan / Hybrid modes

With `enable_subagents: true`, multi-step plans can delegate steps to sub-agents (e.g. `researcher` → `coder` → `reviewer`). See [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## Process model

| Mode | Behavior |
|------|----------|
| `process` (default on Linux/macOS) | Separate OS process — parallelism, isolation |
| `async` | In-process `asyncio` task — lower overhead |

Configured via `subagent_default_process_mode` in profile config.

Sub-agents use the **parent model** (`config.model`), not per-slot `agent_models` (unless you extend the registry).

---

## External CLIs (optional)

Sub-agents do **not** automatically get `external_cli`. To let a sub-agent launch Claude Code / OpenCode in tmux:

1. `holix launch setup` or TUI `/launch` — assign CLI to a sub-agent type (`agent_slot`, e.g. `coder`)
2. Delegate to that sub-agent — it receives the `external_cli` tool when assigned

Details: [LAUNCH_SUBAGENTS.md](LAUNCH_SUBAGENTS.md), [LAUNCH.md](LAUNCH.md).

---

## Logs and limits

- Structured log: `logs/subagent.jsonl` — see [LOGS.md](LOGS.md)
- CLI: `holix logs -s subagent`
- Concurrent limit: `subagent_max_concurrent` (default 4)
- Timeout per job: `subagent_process_timeout` (seconds)

---

## Quick example

```bash
holix tui
```

```text
/subagent-spawn web_researcher Compare Holix vs similar agents; cite sources
/subagents
/subagent-result web_researcher
```

Or in one message to the main agent:

```text
Delegate to coder: add type hints to cli/commands/launch.py and run tests
```

---

## See also

- [LAUNCH_SUBAGENTS.md](LAUNCH_SUBAGENTS.md) — sub-agents vs `holix launch`
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — all `/` commands
- [EXECUTION_MODES.md](EXECUTION_MODES.md) — Plan / Hybrid delegation
- [LOGS.md](LOGS.md) — `subagent.jsonl`