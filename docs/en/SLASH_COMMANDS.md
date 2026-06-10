# Slash commands (`/`)

Slash commands control the session without sending text to the LLM. They work in **TUI** (`helix tui`), **Telegram** (when synced), and partially in **`helix chat-command`**.

Source of truth for TUI/Telegram: `cli/shared/commands/registry.py` and `cli/shared/commands/agent_commands.py`.

## Where each interface supports what

| Command group | TUI | Telegram | `chat-command` |
|---------------|-----|----------|----------------|
| Session (`/new`, `/sessions`, `/switch`) | Yes | Yes | No |
| Copy / transcript (`/copy`, `/open`) | Yes | Limited | No |
| Plan review (`/plan-*`) | Yes | Yes | No |
| Confirm prompts (`/yes`, `/1`–`/4`) | Yes | Yes | No |
| Hub / MCP menus | Yes | Partial | No |
| `/model`, `/skills`, `/memory` | Yes | Yes | Yes (subset) |
| `/compress` | Yes | Yes | Yes |
| `/debug` | Legacy TUI only | No | Yes (`chat-command` only) |

## Keyboard note (macOS RU layout)

On Russian macOS layout, `,help` and `.help` are normalized to `/help`. Type `/` with **Shift+7** when needed.

---

## Help and status

| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/h`, `/?` | Show command help |
| `/status` | — | Profile, execution mode, session id, context (where available) |
| `/metrics` | — | Agent metrics summary |
| `/clear` | `/cls` | Clear transcript (TUI); new conversation id (`chat-command`) |

---

## Models and execution

| Command | Description |
|---------|-------------|
| `/models`, `/model` | Open model picker (TUI) or show current model (`chat-command`) |
| `/mode` | Cycle execution mode, or `/mode <name>` if valid — see [EXECUTION_MODES.md](EXECUTION_MODES.md) |
| `/stream` | Toggle streaming; `/stream on\|off` |
| `/stop` | Cancel running agent tasks |

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
| `/memory-clear` | Clear memory search UI state |
| `/memory clear` | Same as `/memory-clear` |
| `/last` | Full output of last tool |
| `/last N` | Full output of tool *N* back in history |
| `/tools` | List recent tool results |

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
| `/yes`, `/1` | Allow once |
| `/2` | Allow for this session |
| `/3` | Allow always |
| `/no`, `/4` | Deny |

---

## Plan review

When a plan step requires approval:

| Command | Action |
|---------|--------|
| `/plan-confirm` | Confirm current step |
| `/plan-auto` | Auto-execute remaining plan |
| `/plan-refine` | Ask to refine plan |
| `/plan-reject` | Reject plan |

---

## MCP (in-session)

| Command | Description |
|---------|-------------|
| `/mcp` | MCP menu / list |
| `/mcp list` | List configured servers |
| `/mcp install` | Install popular MCP or from git URL |
| `/mcp add` | Manual server config |
| `/mcp assign` | Assign servers to agents |
| `/mcp test <name>` | Test connection |
| `/mcp tools` | List available MCP tools now |
| `/mcp remove <name>` | Remove server config |

CLI equivalent: `helix mcp …` — see [CLI.md](CLI.md#mcp).

---

## Skill Hub (in-session)

| Command | Description |
|---------|-------------|
| `/hub` | Pick catalog (ClawHub, Hermes, Claude, …) |
| `/hub installed`, `/hub list` | Installed hub skills, plugins, MCP |
| `/hub browse` | Browse and install |
| `/hub clawhub` | Open ClawHub catalog |
| `/hub hermes` | Open HermesHub |
| `/hub claude` | Claude official plugins |
| `/hub skills-sh` | skills.sh (query in browser) |
| `/plugins`, `/marketplace` | Alias for hub flow |
| `/skills` | Hint: `helix skills list --agent <role>` |

CLI equivalent: `helix hub …` — see [HUB.md](HUB.md).

---

## Dynamic skill slash commands

Hub-installed skills can register extra commands in:

`{profile}/data/skills/skill-slash.json`

Rebuild after install:

```bash
helix hub slash-sync
```

In TUI, type `/` to see tab-completion; skill commands run the skill workflow for the active agent slot.

---

## `helix chat-command` only

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

## Telegram

Register the bot menu after adding commands:

```bash
helix telegram sync-menu
```

Setup: [TELEGRAM.md](TELEGRAM.md).