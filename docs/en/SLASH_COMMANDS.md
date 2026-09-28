# Slash commands (`/`)

Slash commands control the session without sending text to the LLM. They work in **TUI** (`holix tui`), **Telegram** (when synced), and partially in **`holix chat-command`**.

Source of truth for TUI/Telegram: `cli/shared/commands/registry.py` and `cli/shared/commands/agent_commands.py`.

## Where each interface supports what

| Command group | TUI | Telegram | `chat-command` |
|---------------|-----|----------|----------------|
| Session (`/new`, `/sessions`, `/switch`) | Yes | Yes | No |
| Copy / transcript (`/copy`, `/open`) | Yes | Limited | No |
| Plan review (`/plan confirm|auto|refine|reject`) | Yes | Yes | No |
| Confirm prompts (`/yes`, `/no`; `/1`–`/4` still work) | Yes | Yes | No |
| Hub / MCP menus | Yes | Partial | No |
| `/model`, `/skills`, `/memory` | Yes | Yes | Yes (subset) |
| `/compress` | Yes | Yes | Yes |
| `/debug` | No | No | Yes (`chat-command` only) |

## Keyboard note (macOS RU layout)

On Russian macOS layout, `,help` and `.help` are normalized to `/help`. Type `/` with **Shift+7** when needed.

---

## Help and status

| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/h`, `/?` | Usage guide (Telegram/MAX: scenario buttons; `/help sub` → sub-agents). TUI: command list |
| `/init` | — | Write/update `.holix/HOLIX.md` (project handbook). In chat, phrases like «инициализацию Holix» / `HOLIX.md` run the same path |
| `/status` | — | Profile, execution mode, session id, context (where available) |
| `/metrics` | — | Agent metrics summary |
| `/clear` | `/cls` | Clear transcript (TUI); new conversation id (`chat-command`) |

---

## Models and execution

| Command | Description |
|---------|-------------|
| `/models` | Pick a model. `/model` still works. TUI: provider list, `r` refresh, `d` set default. Telegram/MAX: ↻ Список and «Нажатие: по умолчанию». `holix chat`: `/model refresh`, `/model default <provider> <model>` |
| `/mode` | Cycle execution mode, or `/mode <name>` if valid — see [EXECUTION_MODES.md](EXECUTION_MODES.md) |
| `/stream` | Toggle streaming; `/stream on\|off` |
| `/stop` | Cancel running agent, sub-agents, pending confirmations, and plan reviews (TUI, Telegram, MAX) |
| `/process` | List background processes (**TUI**; live rows are also on the **top** bar). `/process stop` halts one. `/process-stop` still works |
| `/todos` | Show the session checklist from `todo_write` (TUI, Telegram, MAX) |
| `/permission` | Show or set the session OS-sandbox preset: `workspace-write`, `read-only`, `danger-full-access` |
| `/pty` | Persistent shell for this session: `/pty on\|off\|reset` (POSIX) |
| `/change` | SDD git worktree: list, `/change switch <id>`, `/change leave` |

---

## Sessions (TUI / Telegram)

| Command | Description |
|---------|-------------|
| `/new` | Start a new session |
| `/sessions` | List sessions |
| `/switch N` | Switch to session number *N* |
| `/session name <text>` | Rename current session |
| `/profile` | List profiles |
| `/profile <name>` | Switch profile by name |
| `/profile N` | Switch profile by list index |

---

## Memory and tools

| Command | Description |
|---------|-------------|
| `/memory <query>` | Semantic search in agent memory |
| `/memory clear` | Clear memory search UI state. `/memory-clear` and `/memory wipe` still work; wiping stored memory is `/forget` |
| `/last` | Full output of last tool |
| `/last N` | Full output of tool *N* back in history |
| `/tools` | List recent tool results |
| `/trace` | Session trajectory (what tools/the model did). `/trace 80` or `/trace search grep` |

---

## Copy and transcript (TUI)

| Command | Aliases | Description |
|---------|---------|-------------|
| `/copy` | `/copy last` | Copy last assistant message |
| `/copy tool` | `/copy-tool` | Copy last tool output |
| `/copy all` | `/copy-all`, `/copy log` | Copy full transcript |
| `/open` | `/view`, `/transcript` | Open transcript window (F2) for select & copy |

---

## Safety confirmations

When the agent asks to confirm a risky tool:

| Command | Meaning |
|---------|---------|
| `/yes` | Allow once. `/1` still works |
| `/2` | Allow for this session (not listed in the menu) |
| `/3` | Allow always (not listed in the menu) |
| `/no` | Deny. `/4` still works |

---

## Plan review

When a plan step requires approval:

| Command | Action |
|---------|--------|
| `/plan confirm` | Confirm current step. `/plan-confirm` still works |
| `/plan auto` | Auto-execute remaining plan |
| `/plan refine` | Ask to refine plan |
| `/plan reject` | Reject plan |

---

## MCP (in-session)

| Command | Description |
|---------|-------------|
| `/mcp` | Menu. Subcommands: `list`, `install`, `add`, `assign`, `test <name>`, `tools`, `remove <name>` |

CLI equivalent: `holix mcp …` — see [CLI.md](CLI.md#mcp).

---

## Skill Hub (in-session)

| Command | Description |
|---------|-------------|
| `/hub` | Catalog picker. Subcommands: `installed` (`list` still works), `browse`, `clawhub`, `hermes`, `claude`, `skills-sh` |
| `/plugins`, `/marketplace` | Alias for the hub flow |
| `/skills` | Hint: `holix skills list --agent <role>`. Also `pending`, `quality`, `curator` |

CLI equivalent: `holix hub …` — see [HUB.md](HUB.md).

---

## Dynamic skill slash commands

Hub-installed skills can register extra commands in:

`{profile}/data/skills/skill-slash.json`

Rebuild after install:

```bash
holix hub slash-sync
```

In TUI, type `/` to see tab-completion; skill commands run the skill workflow for the active agent slot.

---

## `holix chat-command` only

| Command | Description |
|---------|-------------|
| `/exit`, `/quit`, `/q` | Exit chat |
| `/clear` | New conversation id |
| `/model <name>` | Override model and reinit agent |
| `/profile [name]` | Switch or list profiles |
| `/skills` | List active skills |
| `/memory <query>` | Search memory |
| `/debug` | Debug command help |
| `/debug events [N]` | Last *N* agent events (default 20) |
| `/stream [on\|off]` | Toggle streaming |
| `/compress` | Compress conversation context in DB |

---

## Cron (scheduled tasks)

Gateway must be running. Full guide: [CRON.md](CRON.md).

| Command | Description |
|---------|-------------|
| `/cron` | List jobs (TUI modal / Telegram inline menu). Subcommands: `list`, `add <schedule> :: <task>`, `enable <id>`, `disable <id>`, `remove <id>`, `bind <id>` |

**Auto-create (0.1.16+):** recurring requests in natural language (e.g. «every day at 10 am send news») create a job without `/cron add`. CLI: `holix cron …` — [CLI.md](CLI.md#holix-cron).

---

## Sub-agents and Code mode

Full guide: [SUBAGENTS.md](SUBAGENTS.md). Code mode: [CODE_MODE.md](CODE_MODE.md).

| Command | Where | Description |
|---------|-------|-------------|
| `/subagents` | TUI, Telegram, MAX | Live jobs. Subcommands: `types`, `spawn [--fork] <type> <task>`, `result <job>`, `stop <job>`, `reply <job> <text>`. Older `/subagent-spawn`, `/subagent-terminate`, `/subagent-types` still work |

In TUI, while the agent is busy, a **plain** chat line is queued (not these slash commands). See [TUI.md](TUI.md#prompt-queue).

## Telegram

Register the bot menu after adding commands:

```bash
holix telegram sync-menu
```

Setup: [TELEGRAM.md](TELEGRAM.md).
