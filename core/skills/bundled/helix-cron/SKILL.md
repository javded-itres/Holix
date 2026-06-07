---
name: helix-cron
description: Schedule recurring agent tasks via Helix built-in gateway cron (not crontab or custom scripts)
tags:
  - cron
  - schedule
  - helix
  - gateway
  - periodic
  - automation
user-invocable: true
---

## When to use this skill

The user wants a **recurring or scheduled task** (daily report, hourly check, weekly backup summary, etc.).

**Always use Helix built-in cron** — jobs stored in the profile and executed by the gateway scheduler with the same agent stack as chat.

## Do NOT

- Do **not** create or edit system `crontab`, `launchd` plists, or `systemd` timers for Helix agent work.
- Do **not** write standalone Python/bash “scheduler” scripts that loop with `sleep` unless the user explicitly needs OS-level scheduling outside Helix.
- Do **not** suggest third-party job runners when `helix gateway` can run the task.

## Prerequisites

1. **Gateway must be running** (scheduler lives inside gateway):
   - `helix gateway start` (background) or `helix gateway start -f` (foreground)
   - `helix gateway status` — verify running
2. Jobs are **per profile** (`--profile` / `HELIX_PROFILE`).

## Storage (read-only for debugging)

- Jobs: `~/.helix/profiles/<profile>/data/cron/jobs.json`
- Run log: `~/.helix/profiles/<profile>/data/cron/runs.log`

Prefer **commands** below; edit JSON only if the user insists.

## How to create a job

Tell the user the slash command (TUI / Telegram) or run CLI yourself if you have shell access.

**Slash (chat):**

```
/cron add <schedule> :: <task description>
```

Examples:

- `/cron add every day at 9 :: Summarize yesterday's git activity`
- `/cron add every 30 minutes :: Check disk space and alert if >90%`
- `/cron add 0 9 * * 1-5 :: Morning standup prep from open issues`
- `/cron add hourly :: Quick health check of gateway`

**CLI (terminal):**

```bash
helix cron add "every day at 9 :: Summarize logs"
helix cron list
helix cron disable <job-id>
helix cron enable <job-id>
helix cron remove <job-id>
```

### Schedule formats

- **Natural language** (parsed automatically): `every day at 9:00`, `every 30 minutes`, `hourly`, `daily`, `weekly`, `weekdays`, `every 2 hours`
- **5-field cron** (minute hour day month weekday): `0 9 * * *`, `*/15 * * * *`

Task text after `::` is the **agent prompt** for each run (be specific: what to check, output format, workspace assumptions).

## Manage jobs

| Action | Slash | CLI |
|--------|-------|-----|
| List / UI | `/cron` or `/cron list` | `helix cron list` |
| Enable | `/cron enable <id>` | `helix cron enable <id>` |
| Disable | `/cron disable <id>` | `helix cron disable <id>` |
| Delete | `/cron remove <id>` | `helix cron remove <id>` |

Job IDs are short strings shown in the list (prefix match works).

TUI opens a modal with enable/disable/delete. Telegram has inline buttons under `/cron`.

## Execution behavior

- Scheduler tick runs inside **gateway** (~30s); due jobs start in the background.
- Each run uses conversation id `cron-<job-id>` (separate from the user's chat session).
- The runner prepends context that this is an **automated** run; the model should complete the task and **summarize** results.
- Status fields: `last_run_at`, `last_status` (`success` / `error` / `running`), `next_run_at`, `run_count`.

## Workflow for the agent

1. Clarify **what** should run and **how often** (timezone: server local UTC for croniter unless user specifies).
2. Draft a **clear task prompt** (one-shot instructions, no “ask me later”).
3. Propose exact `/cron add …` or `helix cron add "…"` for the user to confirm, or execute CLI if allowed.
4. Remind to start gateway if not running: `helix gateway start`.
5. After creation, suggest `/cron list` to verify `next_run_at`.

## Natural language → user request

If the user says “every Monday at 10 run X”, translate to:

```
/cron add every week :: X
```

(or `0 10 * * 1 :: X` if they prefer explicit cron).

## Troubleshooting

| Problem | Check |
|---------|--------|
| Job never runs | `helix gateway status`; gateway must be up |
| Invalid schedule | Use `every day at 9` or valid 5-field cron |
| Task runs but fails | Read `runs.log`; fix prompt or model/profile config |
| Duplicate jobs | `/cron list`; remove old rule with `/cron remove` |

## Related Helix commands (not cron)

- `/init` — one-shot project analysis, not periodic
- `helix hub` — skills/plugins, not scheduling