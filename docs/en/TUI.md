# TUI

Full-screen **code-style** terminal UI (`holix tui`). This is the daily driver: chat, slash commands, process bar, prompt queue.

Slash reference lives in [SLASH_COMMANDS.md](SLASH_COMMANDS.md). Do not duplicate it here.

## Start

```bash
cd /path/to/your/project
holix tui
holix tui -p myprofile
```

The session workspace (`.` for tools, `run_terminal_command`, Code mode) is the directory where you launched `holix tui`, not `~/.holix/profiles/<name>/workspace`. Telegram/MAX still use the profile workspace. This override is in-memory and is not written to `config.yaml`.

Web (textual-serve; one session per tab; token required):

```bash
uv sync --extra tui-web
holix tui --web
# http://127.0.0.1:8787/?token=...  (ephemeral token printed if omitted)

# LAN — full agent access; use a strong token
holix tui --web --allow-lan --host 0.0.0.0 --port 8787 --token "$(openssl rand -hex 32)"
export HOLIX_TUI_WEB_TOKEN="..."
```

## Layout (top → bottom)

| Region | What you see |
|--------|----------------|
| **Process bar** | Only **OS-alive** background servers. Hidden when none are running. Click a row for its log. |
| **Todos** | Session checklist from `todo_write`. Hidden when empty. |
| **Transcript** | Chat, tools, confirmations |
| **Prompt queue** | Yellow strip **between** transcript and input — prompts waiting while the agent is busy |
| **Status / context** | Mode, model, tokens |
| **Input** | Multiline prompt. Enter sends; Shift+Enter newline |

The bar at the top is **not** a history of crashed jobs. When a process stops or dies, its row disappears (polled about every 2 seconds).

## Todos

On multi-step work the agent should call `todo_write` with the **entire** list each time (it replaces the previous list). Statuses: `pending`, `in_progress`, `completed`, `cancelled`. The checklist sits under the process bar until cleared (empty list). `/todos` reprints it. The list is a plan, not proof of work.

## Prompt queue

If the agent is still running, Enter **queues** the next message instead of dropping it.

- Queued rows sit between the transcript and the input field.
- Click a row (or **edit**) to load it back into the input.
- **×** deletes that item without running it.
- After the current turn finishes, Holix runs the queue **in order**.
- `/help`, plan-review answers, and sub-agent replies are **not** queued.
- Ctrl+S (`/stop`) stops the current turn; the queue stays so you can edit or drop items.

Limit: 50 pending prompts.

## Background processes

Long-running work (dev server, bot, watch) belongs in `start_background_process`, not `run_terminal_command`.

| Action | How |
|--------|-----|
| View log | Click the **top** process row |
| List | `/process` or `/process list` |
| Stop a server | `/process-stop` |
| Stop the agent only | `/stop` — does **not** kill servers |

If a listed process **dies on its own**, TUI injects a notice and runs (or queues) a turn so the agent can check the log. `/process-stop` does not auto-wake. At most three automatic wakes until you send a real prompt.

Cwd follows `working_directory` → workspace jail → profile workspace. Venv is on `PATH`; `PYTHONUNBUFFERED=1`.

## Trajectory

`/trace` prints an append-only timeline of this session (tools, finals, background processes, todos). `/trace 80` shows more rows; `/trace search grep` filters. Files live in `~/.holix/profiles/<name>/data/trajectory/`. Token-stream deltas are not stored.

## Copy

- **Chat:** select text → bottom **Copy** bar (⌃C/⌘C do not copy the last answer).
- **Copy window (F2 / `/open`):** ⌃C / ⌘C / Ctrl+Shift+C.
- Slash: `/copy`, `/copy tool`, `/copy all`.

## Keyboard

| Key | Action |
|-----|--------|
| Enter | Send (or enqueue if the agent is busy) |
| Shift+Enter | Newline |
| ↑ | Recent prompts |
| `/` | Command menu |
| F1 | Help |
| F2 | Copy window |
| Ctrl+S | Stop current turn |
| Ctrl+L | Clear chat |

On a Russian macOS layout, `,help` / `.help` work as `/help`. Type `/` with **Shift+7** if needed.

## Related

| Topic | Page |
|-------|------|
| Slash commands | [SLASH_COMMANDS.md](SLASH_COMMANDS.md) |
| Skill Hub | [HUB.md](HUB.md) |
| Code mode (`run_code`) | [CODE_MODE.md](CODE_MODE.md) |
| Sub-agent types | [SUBAGENTS.md](SUBAGENTS.md) |
| Cron from chat | [CRON.md](CRON.md) |
