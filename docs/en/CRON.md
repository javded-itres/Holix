# Scheduled tasks (Cron)

Holix includes a **built-in scheduler** that runs inside the **gateway** supervisor. Jobs are stored per profile and executed with the same agent stack as chat — not system `crontab` or external scripts.

Requires a running gateway:

```bash
holix gateway start
holix gateway status
```

Jobs live under `~/.holix/profiles/<profile>/data/cron/`. Run log: `runs.log`.

See also: [CLI.md](CLI.md#holix-cron), [SLASH_COMMANDS.md](SLASH_COMMANDS.md), bundled skill `holix-cron`.

---

## Auto-create from chat (0.1.16+)

When you write a **recurring** request in natural language in **Telegram**, **MAX**, or **TUI**, Holix can create a cron job **before** the agent runs — no `/cron add` needed.

**English examples:**

- `Send me news about AI every day at 10 am`
- `Check disk space every 30 minutes`

**Russian examples:**

- `Присылай мне новости по теме X каждый день в 10 утра`
- `Каждые 2 часа проверяй статус gateway`

Holix replies with job id, cron expression, and `next_run_at` (UTC). If the message was sent from Telegram or MAX, the job is bound to that chat for result notifications.

**What triggers auto-create:**

- Clear recurrence wording (`every day`, `каждый день`, `hourly`, `каждые 30 минут`, `в 10 утра`, …)
- A task body left after schedule phrases are stripped (at least ~8 characters)
- Not a one-shot request (`сейчас`, `just once`)
- Not a help question (`как настроить cron`, `/cron …`)

**What does not auto-create:**

- Messages starting with `/` (use `/cron add` explicitly)
- Vague text without a parseable schedule
- One-shot tasks without recurrence

The agent can also call the **`schedule_cron`** tool (`schedule` + `task`) when auto-detection did not fire.

---

## Manual creation

### Slash (TUI / Telegram / MAX)

```
/cron add <schedule> :: <task description>
```

Examples:

```
/cron add every day at 9 :: Summarize yesterday's git activity
/cron add every 30 minutes :: Check disk space and alert if >90%
/cron add 0 9 * * 1-5 :: Morning standup prep from open issues
/cron add hourly :: Quick health check of gateway
```

### CLI

```bash
holix cron add "every day at 9 :: Summarize logs"
holix cron add "0 9 * * 1-5 :: Standup prep" --name standup
holix cron list
holix cron enable <job-id>
holix cron disable <job-id>
holix cron remove <job-id>
```

---

## Schedule formats

| Style | Examples |
|-------|----------|
| Natural language (EN) | `every day at 9`, `every 30 minutes`, `hourly`, `daily`, `weekly`, `weekdays`, `every 2 hours` |
| Natural language (RU) | `каждый день в 10 утра`, `в 8 вечера`, `каждые 30 минут`, `каждый час`, `по будням` |
| 5-field cron | `0 9 * * *`, `*/15 * * * *`, `0 10 * * 1` |

Text after `::` is the **agent prompt** for each run. Be specific: what to check, output format, workspace assumptions.

`next_run_at` uses **server UTC** (croniter) unless you document timezone expectations in the task prompt.

---

## Manage jobs

| Action | Slash | CLI |
|--------|-------|-----|
| List / UI | `/cron` or `/cron list` | `holix cron list` |
| Enable | `/cron enable <id>` | `holix cron enable <id>` |
| Disable | `/cron disable <id>` | `holix cron disable <id>` |
| Delete | `/cron remove <id>` | `holix cron remove <id>` |
| Bind session | `/cron bind <id>` | — |

- **TUI** — modal with enable/disable/delete.
- **Telegram** — inline buttons under `/cron`; non-admins see only their profile's jobs (isolated mode).
- Job IDs are short strings; prefix match works in CLI.

---

## Execution behavior

- Scheduler tick runs inside **gateway** (~30s); due jobs start in the background.
- Each run uses conversation id `cron-<job-id>` (separate from the user's chat session).
- The runner prepends context that this is an **automated** run; the model should complete the task and **summarize** results.
- Status fields: `last_run_at`, `last_status` (`success` / `error` / `running`), `next_run_at`, `run_count`.
- Optional **notify** targets (`notify_chat_id` for Telegram, `notify_max_user_id` / `notify_max_chat_id` for MAX) receive run summaries.

---

## Troubleshooting

| Problem | Check |
|---------|--------|
| Job never runs | `holix gateway status` — gateway must be up |
| Auto-create did not fire | Rephrase with explicit schedule; or use `/cron add …` or `schedule_cron` |
| Invalid schedule | Use `every day at 9` or valid 5-field cron; avoid ambiguous English like bare `every day at 10 am` without task text |
| Task runs but fails | `holix logs -s cron` or `profiles/<p>/data/cron/runs.log` |
| Duplicate jobs | `/cron list`; remove old rule with `/cron remove` |
| Encrypted profile | Gateway needs `HOLIX_UNLOCK_KEY` for cron runs that touch encrypted memory |

---

## Related

- [GATEWAY.md](GATEWAY.md) — start/stop gateway (scheduler host)
- [TELEGRAM.md](TELEGRAM.md) — bot setup, `/cron` menu policy
- [MAX.md](MAX.md) — MAX bot and auto-create parity
- [LOGS.md](LOGS.md) — `holix logs -s cron`