---
name: holix-subagents
description: >
  Full Holix sub-agent lifecycle: spawn, monitor, collect results, answer ask_user
  questions, approve tool confirmations, and delegate to external CLIs (holix launch).
  Use when the user asks about subagents, /subagent-spawn, delegate_to_subagent,
  background workers, sub-agent questions, /subagent-reply, holix launch + coder,
  or running tasks without blocking the main chat. Invoke via /holix-subagents.
tags:
  - subagents
  - sub-agent
  - delegate
  - background
  - spawn
  - holix
  - launch
  - external-cli
user-invocable: true
---

## When to use

The user wants **background specialized work** without blocking the main Holix chat:

- research, coding, review, writing, analysis
- optional: hand off implementation to **external coding CLIs** (Claude Code, OpenCode, Grok Build) via an assigned `coder` sub-agent

**Always prefer Holix sub-agents** over inventing separate shell scripts or manual tmux unless the user explicitly wants raw terminal control.

## Prerequisites

1. **Enabled** (default on): `enable_subagents: true` in profile `config.yaml` or `HOLIX_ENABLE_SUBAGENTS=true`.
2. **Profile** active: `holix --profile <name> …` or `HOLIX_PROFILE`.
3. **Limits** (profile `config.yaml`):
   - `subagent_max_concurrent` (default 4)
   - `subagent_process_timeout` (seconds per job)
   - `subagent_default_process_mode`: `process` (Linux/macOS, isolated) or `async` (in-process)

If spawn fails with "disabled" → tell user to enable sub-agents and retry.

## Built-in types

| Type | Use for |
|------|---------|
| `researcher` | Deep research, files + web |
| `web_researcher` | Web search + synthesis |
| `coder` | Code write/edit/debug, terminal, tests |
| `analyst` | SQL, data, calculations |
| `reviewer` | Code review |
| `writer` | Docs and content |

Custom types: profile `subagents/types.json`, managed in TUI `/subagent-types` or listed with `/subagent-types list`.

Duplicate active jobs get suffixed ids: `coder-2`, `coder-3`, …

---

## Two ways to start work

### A. Main agent (recommended for natural language)

User asks in chat; **you** (main agent) use tools:

1. `delegate_to_subagent(agent_type, task)` → returns `job_id`
2. Optionally `list_subagents` to check status
3. `wait_subagent_result(job_id)` when the answer must be included in your reply
4. `terminate_subagent(job_id)` to cancel

**Task text rules** — be explicit in `task`:

- **Goal** — one sentence outcome
- **Scope** — paths, modules, constraints
- **Done when** — verifiable criteria (tests pass, file exists, N sources cited)
- **Don't** — forbidden actions if any

Bad: `fix tests`  
Good: `Fix failing tests in tests/test_auth.py; run pytest tests/test_auth.py; report pass/fail and diff summary`

If `delegate_to_subagent` returns `already_running` → call `wait_subagent_result` on that `job_id`, do **not** spawn again.

### B. Direct slash commands (user or you instruct them)

Works in **TUI**, **Telegram/MAX**, and **`holix chat-command`**:

```text
/subagent-spawn <type> <task>
/subagents
/subagent-result <job_id>
/subagent-terminate <job_id>
/subagent-types list
```

CLI chat:

```bash
holix chat-command -p <profile>
```

One-shot via main agent:

```bash
holix run "Delegate to researcher: summarize docs/en/SUBAGENTS.md in 5 bullets"
```

---

## Full lifecycle (monitor → result)

```text
spawn → running → [optional: question / confirmation] → completed | failed | terminated
```

### 1. Spawn

- Tool: `delegate_to_subagent`
- Slash: `/subagent-spawn coder Add type hints to cli/commands/chat.py`

Note `job_id` from the response (often equals type, or `type-N`).

### 2. Monitor

| Method | What it shows |
|--------|----------------|
| `/subagents` | All jobs + **pending questions** |
| `list_subagents` tool | JSON status for main agent |
| `holix logs -s subagent` | Structured `subagent.jsonl` |
| `/subagent-result <job_id>` | Final text when done (or "still running") |

After `/subagent-spawn` in chat hosts, completion may auto-push to transcript when the job finishes.

### 3. Collect result

- **Blocking (main agent):** `wait_subagent_result(job_id)`
- **Non-blocking (user):** `/subagent-result <job_id>`
- On failure: read `error` field / log; offer retry with clearer task or `terminate` + respawn

### 4. Stop

`/subagent-terminate <job_id>` or `terminate_subagent(job_id)`

---

## Questions from sub-agents (`ask_user`)

Process-mode and async sub-agents can call `ask_user`. The parent surfaces a **`SubAgentQuestionEvent`**:

```text
❓ coder: Which auth library should I use — JWT or sessions?
Reply: /subagent-reply coder JWT with refresh tokens
```

### How the user answers (all hosts)

| Input | When |
|-------|------|
| `/subagent-reply <job_id> <answer>` | Always works |
| `@<job_id> <answer>` | Shorthand |
| Plain text message | Only when **exactly one** pending question |

Examples:

```text
/subagent-reply coder-2 use PostgreSQL
@coder use PostgreSQL
use PostgreSQL
```

**Your job as main agent when you see a pending question:**

1. Show the question clearly to the user (quote `job_id`).
2. Tell them the three reply options above.
3. When they answer, ensure it routes via `/subagent-reply` (or plain text if single pending) — **do not** start a new main-agent turn that ignores the sub-agent.
4. After reply, sub-agent continues; poll with `/subagents` or `wait_subagent_result`.

Pending questions appear in `/subagents` under **Pending questions**.

---

## Tool confirmations from sub-agents

When a sub-agent hits a risky tool (`write_file`, `terminal`, …), the parent shows a **confirmation** (may include `subagent_name`).

User approves with slash commands (TUI / chat / messengers):

| Command | Effect |
|---------|--------|
| `/1` or `/yes` | Allow once |
| `/2` | Allow this session |
| `/3` | Allow always |
| `/4` or `/no` | Deny |

Until confirmed, the sub-agent **waits** — remind the user if the job looks stuck at a tool step.

---

## External CLI path (`holix launch`)

Sub-agents do **not** auto-launch tmux CLIs. Flow:

```text
holix launch setup  → assign CLI to sub-agent type (e.g. claude → coder)
main agent → delegate_to_subagent(coder, task)
coder sub-agent → external_cli(action=launch|send|output, cli_id=…)
```

### Setup (once per profile)

```bash
holix launch setup
# Enable claude → Model slot: coder → Assign to sub-agent: coder
```

Check assignments:

```text
/launch list
```

### Manual terminal control (user, not sub-agent)

```bash
holix launch claude
holix launch attach <tmux_session>
holix launch send <id> "refactor auth module"
holix launch chat <id>    # interactive relay
holix launch <id> output
```

### Delegation example (main agent)

```text
User: "Research API in background; implement refactor in Claude Code"

You:
  delegate_to_subagent(researcher, "…")
  delegate_to_subagent(coder, "Launch claude via external_cli and refactor auth in src/auth/")
  wait_subagent_result(researcher)  # when needed for synthesis
```

Rules:

- **Main agent** never has `external_cli` tool.
- Only sub-agent types with `agent_slot` binding get `external_cli`.
- Linux/macOS only for tmux launch.

See profile bindings: `~/.holix/profiles/<profile>/external_clis/`.

---

## Decision guide

| User wants | Do |
|------------|-----|
| Quick background task | `delegate_to_subagent` + inform `job_id` |
| Result in same reply | + `wait_subagent_result` |
| Manual control / slash | Tell user `/subagent-spawn …` |
| Claude Code / OpenCode in terminal | `holix launch setup` + delegate to assigned `coder` |
| Sub-agent asked something | Surface question → `/subagent-reply` |
| Stuck on dangerous tool | Prompt `/1`…`/4` |
| See history | `holix logs -s subagent` |

## Do NOT

- Spawn duplicate jobs for the same running task (use `wait_subagent_result`).
- Run `holix launch` from main agent tools — delegate to assigned sub-agent.
- Assume `holix run` handles `/subagent-spawn` — use `chat-command`, TUI, or tools.
- Block the user chat while waiting — spawn with `wait=False` unless they asked to wait.

## Quick reference

```text
/subagent-spawn writer Draft README section on sub-agents
/subagents
/subagent-reply writer Use MIT license section from LICENSE
/subagent-result writer
/subagent-terminate writer
```

```bash
holix logs -s subagent
holix chat-command -p default
holix launch list
```