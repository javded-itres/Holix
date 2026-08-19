# Changelog

## Unreleased

## 1.0.11 — 2026-08-19

Staged skill proposals (no live write until approve), child jobs on the same ReAct engine as main, and skill-review UX in CLI, API, Telegram, and MAX.

### Added

- **Skill staging** — session self-improve and `skill_manage` open a pending draft; live `SKILL.md` is written only after approve (or auto-apply for high-quality patches). Tools: `skill_view` / `skill_manage`.
- **Quality + curator** — heuristic quality score/tier, duplicate/junk gates, and a deterministic archive of stale agent-created skills (`_archive`, no deletes of protected skills).
- **Learn** — `/learn <hint|url|path>` and `holix skills pending|approve|reject`.
- **Achievements** — skill-hygiene counters next to the skills dir.
- **ReAct sub-agents** — process/async jobs run a filtered `HolixAgent` on the parent graph (honesty, compression, empty-reply continue). Runtime supervisor drains `guidance` / `revise` / `cancel` into the same turn.
- **Messenger review** — Telegram and MAX post staged-skill notices with approve/reject buttons.

### Fixed

- **Unfinished announcements** — «Let me start with…» / «Начну с…» after tools is not a finished step.
- **Empty child replies** — blank LLM output retries instead of closing the job.
- **Timeouts** — `subagent_process_timeout` default 3600s; supervisor idle 300s so a slow model call is not hung. Supervisor knobs are on the runtime config and profile.
- **Textual tool calls** — broader Qwen/Hermes XML recovery; timeout markers treated as aborted finals.

### Tests

- Skill proposal, quality, curator, dedup, live path, tools, slash `assign=True`, live-LLM lifecycle (not in CI).
- Sub-agent ReAct runner, supervisor empty-reply, unfinished-work honesty, textual tool-call recovery, achievements.

## 1.0.10 — 2026-08-17

MCP tools per agent slot, fewer coder tool-loops, and live provider model lists without stale catalog aliases.

### Added

- **MCP by slot** — connect the union of assigned MCP servers, fill popular configs (e.g. Context7), harvest tools when a slow `npx` server becomes ready, and filter tool schemas by agent slot.
- **Process-mode MCP** — child processes start assigned MCP even when the parent profile only had a stub manager.
- **Supervisor loop diagnosis** — structured “what is stuck / what is known / what to fix”; escalate to `ask_user` before stopping a looping sub-agent.

### Fixed

- **Coder loops** — detect service launches across languages; treat inspect/`python -c` and no-op rewrites as non-progress; tighten step-budget and supervisor guidance (venv package hunts, inspect, noop writes).
- **Stale model aliases** — do not inject `default_model` / catalog `popular_models` that `/v1/models` did not return (drops leftovers like `qwen3.8-27b-mac1`).

### Tests

- MCP assignment, service/introspect/test-run signals, step budget, supervisor `ask_user` escalation, live model-id filter.

## 1.0.9 — 2026-08-15

Tool-call recovery and aliases, CPU-safe Chroma embeddings, LangGraph checkpoint size guard, and LTM context-recall tests.

### Added

- **Tool name aliases** — map foreign / leaked tool names to Holix tools so models that invent alternate names still dispatch correctly.
- **Textual tool-call recovery** — recover tool calls embedded in assistant text when the provider omits structured `tool_calls`.
- **File tools** — `grep_files`, `glob_files`, and `delete_file` for safer workspace search and removal workflows.
- **Checkpoint size auto-reset** — when `checkpoints.db` (+ WAL/SHM) exceeds `HOLIX_CHECKPOINT_MAX_MB` (default **200**), Holix deletes and recreates an empty DB on the next graph open; `HOLIX_CHECKPOINT_AUTO_PRUNE` toggles the guard. Does not touch `memory.db` / LTM.
- **reg.ru DNS-01 hooks** — deploy helpers for ACME DNS challenge (`holix-studio-deploy/scripts/dns-hooks/`).

### Fixed

- **Chroma embeddings on weak/CPU hosts** — force ONNX MiniLM on CPU and avoid CoreML paths that stall or misbehave on macOS.
- **Confirmation / tool schema** — tighter alias dedup and confirmation handling for recovered tool calls.

### Tests

- LTM context recall: paraphrase semantic/episodic/strategic search, `memory_retrieval_node` injection, `/forget` vs LTM, profile isolation, path layout.
- Checkpoint auto-prune (over/under limit, cooldown, settings → runtime bytes).
- Tool schema dedup, textual tool-call recovery, chroma embeddings CPU path.

## 1.0.8 — 2026-08-14

Tool confirmation UX, context overflow from huge tool dumps, reasoning-only answers, and test harnesses.

### Added

- **Confirmation policy on the TUI** — status and ready banner show `auto_allow_threshold` / `non_interactive` so it is clear why the confirmation modal may not appear.
- **Unattended / bench policy** — `HOLIX_UNATTENDED` / `HOLIX_BENCH` force `auto_allow_threshold=high` and disable plan review without setting `non_interactive` (which would deny high-risk tools).
- **Env aliases** — `AUTO_ALLOW_THRESHOLD`, `HOLIX_AUTO_ALLOW_THRESHOLD`, `NON_INTERACTIVE`, `HOLIX_NON_INTERACTIVE` documented in `.env.example`.
- **Reasoning-only short answers** — recover explicit `Answer:` / numeric results when the model returns empty `content`.
- **User-case journeys** — `tests/user_cases` (scripted LLM + real tools) and `scripts/test_tui.sh` / `scripts/test_live_llm.sh`.
- **Release skill** — «сделай релиз» / `/make-release` opens a PR, waits for GitHub CI, merges to `main`, and tags the next version.

### Fixed

- **TUI confirmation modal hang** — `/1`–`/4` or agent stop while a modal is open now releases the lock and pumps the next queued confirmation.
- **Runaway tool output** — cap terminal stdout/stderr, graph tool messages, and conversation memory; sanitize oversized tool rows on reload, token usage, and compress so one dump cannot report 600%+ context.
- **DuckDuckGo Instant Answer** — accept HTTP 202 and parse JSON regardless of content-type.
- **Wheel metadata vs twine** — pin hatchling `<1.30` so builds keep Core-Metadata 2.4 (twine 6.2 rejects 2.5).

### Tests

- ConfirmationPresenter queue + external resolve.
- `sanitize_messages_tool_content` bounds token usage.
- Recover short answers from reasoning.
- User-case, TUI Pilot, and live-LLM harnesses (`live_llm` stays out of CI).

## 1.0.7 — 2026-08-08

Terminal safety when whitelist is off, and SDD archive merge gates.

### Fixed

- **Destructive terminal patterns with whitelist off** — `HOLIX_TERMINAL_COMMAND_WHITELIST=false` still blocks `rm -rf`, `curl|sh`, `mkfs`, `dd`, shutdown/reboot, etc. (`blocks_dangerous_patterns` always applied).
- **SDD archive without merge** — `archive` refuses to move a change unless delta specs merge into main `openspec/specs/<domain>/spec.md` (unless `force=true`).
- **Plan path resolution** — relative plan paths resolve against profile `workspace_root`, not process CWD (Studio list/open plans).

### Tests

- Terminal dangerous patterns when whitelist is disabled.

## 1.0.6 — 2026-08-05

Agent reliability for messengers: anti-monologue pipeline, classic/modern switch, background process history, and workspace access for admin (jail-off) profiles.

### Added

- **Agent pipeline switch** — `classic` (≈1.0.2 quiet UX) vs `modern` (full anti-monologue honesty); Telegram/MAX menu + `HOLIX_AGENT_PIPELINE` (default classic).
- **Reflexion / meta toggles** — Telegram and MAX status menus can turn self-refinement on/off (default off on production profiles).
- **Pin background process notices** — Telegram pins a process message with stop; MAX pins in groups when admin.
- **Background process history** — stopped rows stay in `background_processes.json` (up to 30 days) with restart command via `list_background_processes`.
- **Chat max_tokens default 8192** — `HOLIX_AGENT_CHAT_MAX_TOKENS` raised to reduce mid-answer truncation loops.
- **Content-loop metrics** — `/metrics` reports `content_loop_collapsed`.

### Fixed

- **Monologue collapse** — harden `collapse_repetitive_text` for `bot.py` dots, mid-loop typos (`bot_bot`), ellipsis-glued spam; stream abort + hard-trim; classic path never ships multi-KB loops.
- **Classic mid-task stop** — force tools on action requests; never finish on «сделаю/создаю/запускаю» without tool calls; pathological loops nudge on classic too.
- **Truncation notice not final** — modern does not treat system truncation wall as a completed task.
- **Own workspace when jail off** — admin/ops may `mv`/`cp` into `…/profiles/<name>/workspace`; secrets and other profiles stay blocked.
- **Clear access-denied terminal errors** — sudo / Permission denied explained in RU for the agent and user.
- **Untracked bot launches** — block long-running bots/servers via `run_terminal_command` (use `start_background_process`).
- **Messenger status streaming** — no live monologue paint when the answer is posted separately.
- **Ruff I001** — import order in Telegram/MAX interactive pickers (CI).

### Tests

- Monologue collapse with `bot.py` + typo variant; classic patho honesty; terminal workspace allow when jail off; background process stopped history; access-denied messages.

## 1.0.5 — 2026-08-05

Messenger reliability: no draft-answer spam, think-tag stripping, and UX toggles.

### Added

- **Sub-agents menu toggle** — Telegram/MAX `/status` panel can enable or disable `enable_subagents` for the active profile (persisted + live agent tools sync).

### Fixed

- **Draft FinalResponse spam** — successful ReAct drafts no longer emit `FinalResponseEvent` before Reflexion; messengers receive a single final after the graph finishes (stops TG/MAX monologue spam like «Что сделаю… Начинаю»).
- **Think/CoT markup in content** — strip `<think>…</think>` and similar tags from assistant text before delivery.
- **Plan monologue without tools** — honesty nudge when the model only narrates a plan («Что сделаю», «Начинаю») without tool calls.
- **Subagent metering** — emit `LLMCallCompleted` for model.calls dashboards on sub-agent runs.
- **Terminal whitelist** — honor profile whitelist toggle over systemd env.
- **Subagent confirmations** — stamp parent `conversation_id` on tool confirmations.

### Tests

- Strip think markup; plan monologue honesty; react defers FinalResponseEvent; messenger subagents settings.

## 1.0.4 — 2026-08-04

Plan-mode UX, OpenTelemetry GenAI conventions, and SDD safety during planning.

### Added

- **Plan-build live progress** — `ThinkingEvent` phases while the plan is generated (context, handbook, LLM wait heartbeats every ~12s, quality retries, save/ready) so Studio/Telegram show the agent is working.
- **OpenTelemetry GenAI** — optional `Holix[otel]` instrumentation (`core/monitoring/genai_otel.py`) with GenAI semantic-convention spans (`chat {model}`, `plan holix`) and token/duration metrics; auto-setup when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Docs: [OBSERVABILITY.md](en/OBSERVABILITY.md).
- **Meta/reflect token metering** — MetaAgent analyze/evaluate emit `LLMCallCompletedEvent` with duration for Studio dashboards.

### Fixed

- **Plan mode must not bootstrap SDD** — planning only **reads** `openspec/` and may run `/init` for `HOLIX.md`; no `sdd_init` / `sdd_apply` / `sdd_propose` in plan prompt tools or generated steps.
- **CI** — drop private `holix-studio` git pin from `uv.lock` so public Actions can `uv sync` without private-repo credentials.

### Tests

- Plan progress, GenAI OTEL no-op, plan SDD guard, planning context (no sdd_init suggestion).

## 1.0.3 — 2026-08-03

Plan orchestration quality, SDD task sizing, and runtime/resource fixes since 1.0.2.

### Added

- **Stable plan identity** — `plan_id` stays in graph state so draft and confirm overwrite one plan file instead of spawning orphans; progress persists and confirmed plans resume without re-review.
- **Plan step checkboxes** — GFM checkboxes track step status through execution; markdown builder/parser keep progress in the plan document.
- **Planning context** — when planning, load `HOLIX.md` and OpenSpec specs; run `/init` pre-scan if the handbook is missing (`core/project/planning_context.py`).
- **Workspace root resolve** — `/init` and planning context resolve against the project workspace root (`core/project/workspace_root.py`).
- **SDD task sizing & resource limits** — task sizing helpers, runtime resource limits (including safe skip of `systemd-run --scope` when Access denied), and subagent runtime registry improvements.

### Fixed

- **Hybrid / auto orchestration** — hybrid mode aligned with plan step orchestration; routers and step orchestration share the same plan-step path.
- **Reasoning-only LLM text** — plan steps no longer treat empty/reasoning-only model responses as final answers.
- **Plan review guard** — resolve the active review guard from the current agent instance (fixes stale guard after rebinds).
- **Telegram messenger admin** — fall back to process environment when profile env lacks admin id.

### Tests

- Plan dedupe, resume, review, planning context, workspace root, step orchestrate, resource limits, react timeout/reasoning empty.

## 1.0.2 — 2026-07-31

Runtime orchestration, Reflexion, A2A, production Docker, and multi-user deploy ergonomics.

### Added

- **A2A (Agent2Agent)** — Holix as A2A **server** (Agent Card + JSON-RPC `/a2a` + REST + **SSE streaming** via `message/stream` / `/a2a/message:stream`) and **client** (`a2a_list_agents`, `a2a_discover`, `a2a_send_message`, `a2a_get_task`). Profile `a2a:` config / `HOLIX_A2A_*`. Docs: [A2A.md](en/A2A.md).
- **Reflexion (main agent)** — after a draft answer, meta evaluator scores quality (+ tool trajectory); low scores inject verbal self-feedback and retry ReAct (`reflect` node). Defaults: `enable_meta_agent` / `enable_self_refinement` **on**. Docs: [EXECUTION_MODES.md](en/EXECUTION_MODES.md#reflexion-self-critique).
- **Step budget extension** — at `max_steps`, health-check may grant more steps when the agent is still progressing (`HOLIX_MAX_STEPS_EXTEND_*`). Applies to main graph/legacy loop and sub-agents.
- **Subagent supervisor (runtime)** — background watcher detects loop / thrash / hang / stall and injects **guidance** into the same job (async + process). Events: `SubAgentSupervisorEvent`.
- **Subagent supervisor (graph)** — in `plan_and_execute`, after `collect`: rework failed wave jobs with repair instructions; merge keeps successes (`prior_job` supersede). Design: [SUBAGENT_SUPERVISOR.md](en/SUBAGENT_SUPERVISOR.md).
- **Docker production stack** — `docker-compose.yml` (full agent / gateway-only / Ollama profiles), `docker-compose.prod.yml`, `docker/env.example`, entrypoint modes (`agent`, `gateway`, extensions pip/drop-in), bootstrap for profile `shared` + workspace jail. Docs: [INSTALLATION.md](en/INSTALLATION.md#path-b--docker).

### Changed

- Default `subagent_default_process_mode` documented as **`async`** (process still available with spawn fallback).
- Mode graphs wire `meta_agent` and `reflect` into `react`, `hybrid`, and `plan_and_execute`.
- Companion autostart flags: `HOLIX_TELEGRAM_AUTOSTART` / `HOLIX_MAX_AUTOSTART` for gateway-only containers.
- Docker default profile is **`shared`** (production-safe; `default` remains dev-only).

### Docs

- Updated EN/RU: EXECUTION_MODES, SUBAGENTS, CONFIGURATION, ARCHITECTURE, MEMORY, INSTALLATION, DEPLOYMENT; supervisor design plan under `docs/plans/`.

## 1.0.1 — 2026-07-29

Patch release focused on **tool isolation**, **gateway security**, and **cooperative cancel** so Studio/agent runs fail closed on secrets and stay killable.

### Fixed

- **`execute_python`** — runs in a **subprocess** with restricted builtins; safe `__import__` for allowlisted modules (fixes `ImportError: __import__ not found`); cooperative cancel + hard timeout kill process tree
- **Terminal cancel** — `run_terminal_command` honours run cancellation and kills the process group on cancel/timeout
- **Workspace jail** — absolute paths under the profile workspace allowed when jail root is set; profile secrets / `$HOLIX_HOME` / caches stay blocked
- **Hub HTTPS** — hub source fetch prefers HTTPS and records commit SHA when available
- **Subagents** — safer spawn/store handling for custom types and cancel/status paths
- **Gateway / API keys** — profile-scoped API key permissions; confirmation and permission checks tightened for unattended / high-risk tools
- **Hermes runs** — run status transitions and cancel semantics (avoid marking cancelled too early; respect exec/read capability checks)

### Security

- Block shell access to Holix profile directories and secrets even when workspace jail is off
- Unattended contexts cannot run unrestricted python/node-style tooling without permission
- Shared permission/confirmation state across parallel agents improved for Studio multi-run

### Tests

- `tests/test_code_executor.py`, `tests/test_terminal_cancel.py`, `tests/test_hub_https.py`, `tests/test_api_key_profile_scope.py`

## 1.0.0 — 2026-07-25

**First stable major release.** Holix graduates from the 0.1.x beta line to a production-oriented 1.0 API for the agent runtime, extension ecosystem, messenger hosts, and gateway.

### Highlights

- **Extension platform** — installable host/agent extensions via `holix-sdk`, drop-in folders, sidecars, Telegram/MAX plugin APIs, and agent self-extension (local only)
- **SDD + subagent runtime** — structured task graph, registry, and hardened gateway orchestration for multi-step work
- **Messenger production** — MAX Long Polling as supervised OS subprocess; billing auto-onboard; dual-path health for extensions
- **Studio companion (optional package)** — browser IDE, workspace tree, agent WebSocket, preview origins
- **Security** — shared `PermissionManager` across parallel agents; terminal whitelist extras can be removed; Windows path/whitelist fixes
- **Browser** — WebM session recording tools for agent-driven browser work
- **Docs** — holix-docs site: full Extensions + holix-sdk guides (RU/EN), self-extension modes, Support Desk tutorial examples

### Added

#### Extensions & holix-sdk
- **Extension framework** — discovery of host (`holix.extensions`) and agent (`holix.agent.extensions`) entry points plus profile/global drop-in folders
- **`holix-sdk`** — stable public package for extension authors (`ExtensionBase`, `AgentExtensionBase`, capabilities, host/i18n/models bridges)
- **Gateway companions** — host extensions mount FastAPI routes and optional **sidecars** on `holix gateway start`
- **Messenger plugin APIs** — `register_telegram` / `register_max`: commands, handlers, message gates, access checks, callbacks
- **Agent self-extension** — tool `manage_agent_extensions` (list/create/disable/enable/reload/quarantine); skill `/holix-extensions`
- **Hot-reload** — local CLI/TUI sessions load new drop-in tools without full process restart
- **Self-extension policy** — create/reload allowed only in **local single-operator** mode; denied on multi-user Telegram/MAX hosts (`HOLIX_SELF_EXTENSIONS` override)
- **Kill-switches** — `agent_extensions_control.yaml`, `HOLIX_AGENT_EXTENSIONS_OFF`, `HOLIX_AGENT_EXTENSIONS_DISABLED`
- **Reference package** — `packages/holix-extension-demo` (tool, slash, LLM middleware)

#### SDD & agents
- **SDD task graph** — structured change/task execution model
- **Subagent runtime registry** — lifecycle tracking, binding slots, gateway-oriented orchestration
- **Layered architecture / DI providers** — cleaner runtime composition and action honesty paths

#### Studio (optional holix-studio extension)
- **MVP local serve** — IDE panel, Monaco editor, agent chat over WebSocket
- **Workspace tree** — create/upload/move/delete files and directories; CWD display
- **Agent chat** — streaming init, markdown preview, resizable/collapsible panels
- **Preview** — browser preview preference; FE/BE public origins and Vite HMR guidance for agents
- **Profile credentials** — Studio login material generated on profile create when applicable

#### Runtime & tools
- **Browser video** — WebM recording tools for agent sessions
- **Background processes** — `list_for_profile` on process registry; better Next.js/generic port detection from logs
- **Security** — remove terminal whitelist extras; share profile `PermissionManager` across parallel agents

#### Messengers
- **MAX** — Long Polling runs as OS subprocess under gateway supervisor (avoids in-process hang); explicit polling allowed in production
- **Billing auto-onboard** — when billing is enabled, skip admin approval queue for MAX (and consistent TG path)
- **Extension instance fix** — gateway `mount_gateway` uses the same host extension instances as `on_startup` (stateful billing/health)

#### Documentation (holix-docs site)
- Full **Extensions** guide (RU/EN): architecture, install, drop-ins, self-extension modes, Support Desk tutorial (no Studio/billing product docs on that page)
- Dedicated **holix-sdk** reference with module map and code samples
- Site nav + SEO for `extensions` and `holix-sdk`

### Fixed

- **MAX hang** — concurrent in-process agent creation under polling replaced by supervised subprocess
- **Empty billing health providers** — host extension remount no longer loses `_service` state
- **Webhook FastAPI 422** — nested `Request` import treated as query param; module-level import pattern documented
- **Windows** — path handling, terminal whitelist aliases (`ls`/`cp` style), CI-portable tests
- **Env bootstrap** — shell-lock behavior and `/v1/models` profile routing in tests
- **Agent** — skip unreadable directories when discovering `HOLIX.md`
- **Ports** — treat listening sockets as busy; Windows/Unix listener detection
- **Studio** — WebSocket delivery, auth-free static assets, file tree move/delete, spurious end-of-run errors, SaaS workspace ownership / browser preview preference
- **Ruff / CI** — lint cleanups, security extras in CI, subagent binding slot bug

### Changed

- **Version** — package `Holix` **1.0.0** (semver major: production/stable classifier; extension contracts documented as SDK API v1)
- **PyPI classifier** — `Development Status :: 5 - Production/Stable` (was Beta)
- **Messenger hosts** — force `self_extensions_enabled=False` for Telegram/MAX multi-user agents
- **Extension mount lifecycle** — CLI and gateway registration iterate `_loaded_extensions` after startup (same instances)

### Security

- Parallel agents on one profile share permission state consistently
- Terminal whitelist extras removable without full reset
- Multi-user bots cannot self-author extensions into shared agent state by default

### Upgrade notes (0.1.x → 1.0.0)

1. **Install:** `pip install -U Holix` or `pipx upgrade Holix` (or your pinned deploy image).
2. **Python:** still requires **≥ 3.12**.
3. **Extensions:** authors should depend on `holix-sdk>=0.1.0` and declare `requires_holix` appropriately; drop-ins under `~/.holix/profiles/<p>/extensions/` continue to work.
4. **Self-extension:** only local CLI/TUI; Telegram/MAX bots return `self_extensions_denied` on create/reload.
5. **MAX:** ensure gateway supervisor starts MAX as subprocess (default after this release); restart gateway after upgrade.
6. **Host webhooks:** import FastAPI `Request` at module level (not inside nested handlers) to avoid HTTP 422.
7. **Breaking expectations (behavioral, not silent renames):**
   - Multi-user messengers no longer allow agent-authored drop-ins.
   - Extension HTTP mounts must not assume a second discover cycle creates a fresh service instance for webhooks.
8. **Optional products** (billing, studio) remain separate packages; core 1.0.0 does not require them.

### Documentation

- `docs/en|ru/EXTENSIONS.md` — expanded author + operator guide
- holix-docs: `/docs/extensions`, `/docs/holix-sdk` (deployed site)

## 0.1.21 — 2026-07-06

### Added
- **Telegram sub-agent background delivery** — results are sent asynchronously so chat handlers are not blocked for minutes
- **Web-research dispatch** — `search_intent` / `web_research` modules and `web-researcher` bundled skill for explicit sub-agent research requests
- **`subagent_owner` pinning** — `/subagents` lists handles after spawns even when the main agent is re-initialized

### Fixed
- **Telegram sub-agent silence** — log send failures; deliver results on `delegate_to_subagent` completion
- **Agent init race** — serialize Telegram agent initialization with a per-chat lock

### Changed
- **Sub-agent delegation** — only on explicit user request (`/subagent-spawn`, delegate tool), not automatic web-search routing
- **Version** — package `Holix` 0.1.21

## 0.1.20 — 2026-06-26

### Fixed
- **Cron jobs never running** — scheduler no longer pre-registers wrapper tasks, so `run_cron_job` is not self-skipped with “already running”
- **Strict LLM providers (tool ordering)** — defer context notes during tool-call turns; repair orphan `tool` messages after context truncation (Groq/Mistral `role 'tool' after role 'user'`)

### Changed
- **Version** — package `Holix` 0.1.20

## 0.1.19 — 2026-06-25

### Fixed
- **Strict LLM providers (Groq, Mistral, LiteLLM)** — sanitize chat history before API calls: strip `agent_soul` metadata, fold extra `role:system` turns into user context notes (fixes [#41](https://github.com/javded-itres/Holix/issues/41))

### Changed
- **Version** — package `Holix` 0.1.19

## 0.1.18 — 2026-06-23

### Fixed
- **Empty model responses** — pass `max_tokens` (default `8192`, env `HOLIX_AGENT_MAX_TOKENS`) in ReAct steps so reasoning models (`coder`, `smart`) return visible answers
- **Telegram vision** — use `resolve_assistant_text` for reasoning-only vision completions

### Changed
- **Version** — package `Holix` 0.1.18

## 0.1.17 — 2026-06-21

### Added
- **Global cron scheduler** — one gateway tick loop runs due jobs across all Holix profiles; per-profile job storage and visibility unchanged
- **Cron profile index** — mtime-cached `jobs.json` discovery, periodic full scan, `HOLIX_CRON_MAX_CONCURRENT` run limit
- **Telegram image router** (optional) — classify image overviews and route to specialist vision models (`HOLIX_TELEGRAM_IMAGE_ROUTER_ENABLED`)

### Fixed
- **Cron not running for user profiles** — jobs created under `admin` (or any mapped profile) execute when gateway runs on `docs`
- **Telegram attachments** — store files under the named Holix profile, not shared `data_dir`
- **Telegram gateway startup** — start polling before per-user menu registration; skip eager `set_my_commands` on boot; typing during agent init
- **Telegram vision** — prefer vision-capable LiteLLM aliases (`vision-auto`, `gemini-flash`, `auto`) over text-only models

### Changed
- **Version** — package `Holix` 0.1.17
- **Cron worker** — standalone worker schedules all profiles by default (`--profile` kept for legacy single-profile mode)

### Documentation
- **Information architecture** — one canonical page per topic; merged multi-profile and launch-subagents docs into TELEGRAM, MAX, SUBAGENTS
- **INSTALLATION** (EN/RU) — unified Path A (uv/pipx) and Path B (Docker); QUICKSTART → START_HERE cheat sheet
- **USER_GUIDE** — learning path with links only (removed from site nav)
- **Site /docs** — regrouped sidebar (install, daily use, agents, integrations, reference); CLI moved to end
- **MCP, MODELS, MEMORY** (EN/RU) — dedicated canonical pages; CONFIGURATION links instead of duplicating
- **RU parity** — ARCHITECTURE and LOGS full translations; LICENSING_STRATEGY (RU) + EN stub
- **holix-docs** — nav/SEO for mcp, models, memory; client redirects (quickstart→start-here, merged stubs); marketing links to subagents

## 0.1.16 — 2026-06-18

### Added
- **Cron auto-create from chat** — recurring requests in natural language (RU/EN) in Telegram, MAX, and TUI automatically create gateway cron jobs; `schedule_cron` agent tool as fallback
- **Russian schedule parsing** — `каждый день в 10 утра`, `в 8 вечера`, `каждые 30 минут`, etc.
- **Unified `/stop`** — `cli/shared/agent_stop.py` cancels agent workers, run tasks, confirmations, plan reviews, and sub-agents (TUI, Telegram, MAX)
- **TUI process viewer** — modal to list/stop background processes; `/process` and `/process-stop` slash commands
- **Background process paths** — `core/runtime/background_paths.py`: cwd from `working_directory` → jail → workspace; venv in PATH, `PYTHONUNBUFFERED`
- **Port-aware cleanup** — `cleanup_before_start` stops only same-session processes or port conflicts (not all profile processes)

### Fixed
- **Plan mode** — sub-agent delegation and reasoning-only stalls; plan review flow improvements
- **Cron schedule parser** — `every day at 10 am` no longer misparsed as 5-field cron
- **Terminal safety** — Holix profile dirs and `.runtime-cache` blocked even when workspace jail is off
- **`/init` locale** — runs in profile UI language (`/lang ru` | `en`)
- **Background shell** — `bash -lc` instead of fragile `exec source …` for venv activation

### Changed
- **Version** — package `Holix` 0.1.16

### Documentation
- **CRON** (EN/RU) — dedicated page: auto-create from chat, schedule formats (RU/EN), `/cron`, `holix cron`, `schedule_cron`
- **SLASH_COMMANDS, CLI, TUI, USER_GUIDE, TELEGRAM, TERMINAL_SECURITY** (EN/RU) — `/stop`, `/process`, cron auto-create, Holix path blocking without jail
- **holix-docs** — version 0.1.16, `cron` nav slug, SEO, synced content

## 0.1.15 — 2026-06-15

### Added
- **Development plan report (Plan & Hybrid)** — before execution, the agent shows an 8-section BA-style approval document: summary, stages, priorities, dependencies, risks, manual actions, estimates, recommended stack; plus execution steps
- **Plan clarification step** — when the task is ambiguous (`needs_clarification`, `clarifying_questions`), the agent asks questions **before** plan approval; answers regenerate the plan; reply `продолжай с допущениями` / `proceed with assumptions` to skip
- **Project plan storage** — confirmed plans saved to `./.holix/plans/` (`.md` + `.json`); planner reads existing plans from this directory by default
- **Plan generation tuning** — `plan_generation_timeout` default 600s, `plan_generation_max_tokens` 12000; timeout retries increase time instead of cutting tokens; truncated JSON triggers retry
- **`holix launch`** — external coding CLIs in tmux (Linux/macOS): setup wizard, per-profile bindings, session management (`attach`, `send`, `chat`, `output`, `kill`)
- **Supported agents** — Claude Code, OpenCode, Grok Build, GigaCode, Aider; per-agent `holix launch <id>` and `holix launch <id> status`
- **Holix profile models in external CLIs** — Claude gateway/LiteLLM env; OpenCode via generated `opencode.json` + `OPENCODE_CONFIG` (`holix/<model>`); Grok Build via `config.toml` + `GROK_HOME` and positional initial task
- **Auto-install** in `holix launch setup` for curl/npm/uv installers (OpenCode, Grok Build, Claude, Aider); binary detection in `~/.opencode/bin`, `~/.grok/bin`, …
- **Interactive relay** — `holix launch chat` forwards text and terminal keys (arrows, Tab, Esc, digits 1–9) to tmux panes
- **Agent tool** — `external_cli` for launch/send/output/list_sessions (assigned sub-agents only)
- **Sub-agent CLI assignment** — `holix launch setup` field **Assign to sub-agent** (`agent_slot` in bindings); tool injected only for matching sub-agent types
- **TUI `/launch`** — modal to assign or unassign sub-agents per external CLI; `/launch list` in transcript
- **Sub-agent types** — profile `subagents/types.json`, TUI `/subagent-types` (prompt, skills, MCP, model, external CLI)
- **Docs** — [SUBAGENTS.md](en/SUBAGENTS.md) (EN/RU): sub-agent types, spawn, slash commands, limits, custom type wizard
- **Docs** — [LAUNCH.md](en/LAUNCH.md), [LAUNCH_SUBAGENTS.md](en/LAUNCH_SUBAGENTS.md) (EN/RU), CLI reference sections

### Changed
- **Versioning** — package version is fixed manually in `pyproject.toml` and `cli/__init__.py`; Hatch auto-bump on `uv build` removed
- **`holix tui`** — always launches the code-style TUI; legacy dashboard removed (`HOLIX_TUI_LEGACY` no longer supported)
- **`external_cli` access** — main agent no longer has the tool; launch/send/output require an enabled binding whose `agent_slot` matches the calling sub-agent type
- **Codex CLI and Codex App** — temporarily removed from `holix launch` registry
- **Plan directory** — `./.holix/plan/` renamed to `./.holix/plans/` (legacy `plan/` still listed when reading)
- **Sub-agent default mode** — `subagent_default_process_mode` default `async` (with process spawn fallback on macOS)

### Documentation
- **EXECUTION_MODES** (EN/RU) — clarification flow, development report, plan storage
- **CONFIGURATION** (EN/RU) — plan generation env vars, `.holix/plans/`

## 0.1.14 — 2026-06-14

### Added
- **MAX messenger integration** — multi-user bot parity with Telegram: per-profile `max.env`, allowlist, user map, admin CLI (`holix max map`, `max requests`, `max admin`), access requests, profile auth/seed, `holix_max` gateway API
- **MAX UX** — live presenter, separate final answer, approval short tokens, outbound file delivery, typing indicator, user removal helpers
- **Shared messenger layer** — `integrations/messenger/` for access requests, user profiles, final content normalization, user removal
- **Gateway companions** — MAX webhook reload on `gateway reload`, `gateway status` / `max status` summaries, doctor parity
- **Profile name validation** — path-injection guard for profile names and paths under `~/.holix/profiles`
- **Live UI i18n** — localized messenger progress labels per profile locale
- **LLM response helpers** — `core/llm/` utilities for extracting agent text from provider responses
- **Docs site decoupling** — remove bundled `web-docs/`; gateway worker sets `HOLIX_WEB_DOCS_DIR` when unset (external holix-docs repo)

### Fixed
- **Messenger final answers** — stream accumulated text when LLM returns placeholder final; prefer tool/subagent results over preamble
- **Gateway startup** — skip invalid profile names in runtime cache; auto-detect web-docs directory
- **Tests** — hub slash registry under profiles root, whitelist env via `HOLIX_HOME`, mock agent profile name coercion
- **CI** — ruff import fixes across MAX/Telegram modules

### Changed
- **Version** — package `Holix` 0.1.14 on PyPI

## 0.1.13 — 2026-06-13

### Added
- **Profile encryption at rest** — optional AES-256-GCM for profile `.env`, `SOUL.md`, `USER.md`, `telegram.env`, SQLite memory (`memory.db`, `ltm.db`, checkpoints), and Chroma vector store; Argon2id-wrapped DEK in profile metadata
- **`HOLIX_ENCRYPTION_MODE`** — policy `off` / `linux-production` / `on`; Linux production path auto-enables encryption on supported hosts; mode is OS-scoped, not gated only on `HOLIX_ENV`
- **Gateway profile unlock** — `HOLIX_UNLOCK_KEY` unlocks encrypted profiles in gateway/API; invalid key treated as locked for memory access
- **Gateway seal** — lock encrypted profiles after gateway stop; multi-profile API unlock flow (PR-6)
- **`holix profile crypto`** — enable/disable encryption, migrate unencrypted profiles, bulk workspace migration, `decrypt-workspace` for legacy encrypted agent files
- **Platform-managed quotas** — per-profile workspace size limits reconciled on create/profile ops
- **Runtime cache hardening** — stale gateway/runtime cache recovery; deploy scripts for dedicated `holix` system user (`deploy/scripts/setup-holix-runtime-user.sh`, gateway seal helper)
- **Profile deletion** — `holix profile delete` (`--yes`, `--skip-notify`); `DELETE /api/holix/profiles/{id}?notify=true`; optional Telegram notify to mapped users; protected profiles `default`, `docs`, `global`
- **Workspace path privacy** — jailed profile users see workspace-relative paths in tool output and agent replies; Telegram admin and gateway `admin` API keys still see absolute paths
- **Sub-agent orchestration** — `plan_and_execute` can run coordinated multi-agent waves; spawn results return reliably to the parent session
- **Gateway lifecycle** — `holix gateway reload` (config/companion refresh) vs `holix gateway restart` (full stop/start); docs companion port preserved across reload
- **Hermes API** — `GET /v1/models` lists configured LLM models from active profile; `/v1/runs/{id}` poll returns terminal `status` compatible with Hermes clients
- **Production admin profile** — when `HOLIX_ENV=production`, auto-create `admin` Holix profile and copy settings from `default` (config + env overrides) on gateway start, env change, and `--set-admin` approval
- **Telegram menu policy (isolated mode)** — per-user slash-command menu; non-admins do not see `/message` or `/init`; `/cron` and read-only `/mcp` show only the user’s own profile tasks/servers; `/status` panel hides Profile picker for non-admins
- **Telegram UX** — agent final answer posted as a separate message (live card shows progress only); approval/plan callback tokens hardened (short `callback_data`, idempotent double-tap, `/yes` fallback); no expiry on confirmation/plan-review waits
- **Encrypted env editing** — `holix profile env --edit` and `gateway configure` read/write encrypted profile `.env`; decrypt-aware dotenv loaders across CLI, API, and Telegram

### Security
- **Auth and IDOR** — close cross-profile access gaps in management API; stricter profile-scoped permissions; block risky shell chaining patterns in terminal tool policy
- **Production profile policy** — implicit `default` profile blocked when `HOLIX_ENV=production`; explicit named profiles required (`holix -p <name> …`)

### Fixed
- **Gateway startup** — defer agent warmup to background task so Telegram polling is not blocked for minutes; avoid duplicate cron/Telegram companions when supervisor manages the process; profile registry init moved off the event loop via `asyncio.to_thread`
- **Gateway Telegram on `uv tool install`** — require `uv tool install ".[telegram]"` (or `--with aiogram`); bot no longer silently skipped when token lives only in encrypted `telegram.env`
- **Telegram env loading** — empty `TELEGRAM_BOT_TOKEN` in shell/global no longer masks token from encrypted `telegram.env`; gateway loads `telegram.env` after unlock
- **Telegram user mapping fallback** — gateway host profile can read bindings from `default/telegram-users.json`
- **Workspace plaintext policy** — agent `workspace/` stays unencrypted (git-friendly); outbound Telegram attachments decrypt legacy encrypted workspace files once
- **Crypto edge cases** — read encrypted `telegram.env` without raw UTF-8 decode; `HOLIX_UNLOCK_KEY` invalid → memory locked; Linux-only production encryption enforcement
- **SQLite paths** — API keys DB and profile memory DBs resolve under `HOLIX_HOME` (fixes from 0.1.12 carry-over validated on multi-profile gateway)
- **CI portability** — encryption, runtime cache, path, and locale tests isolated from developer machine env

### Documentation
- **PROFILE_ENCRYPTION** (EN/RU) — dedicated site page: encrypted vs plaintext assets, OS policy table, unlock key, gateway/systemd, workspace migration
- **Path visibility** — PROFILES mermaid flow, gateway API table, Telegram/USER_GUIDE callouts, TROUBLESHOOTING FAQ (EN/RU)
- **Profile delete, encryption, Telegram deploy** — PROFILES, CLI, GATEWAY_API, TELEGRAM, DEPLOYMENT, CONFIGURATION, SECURITY (EN/RU); web-docs rebuilt
- **SEO** — `profile-encryption` slug in sitemap/nav; updated meta for profiles, configuration, security, deployment, telegram

### Changed
- **Confirmation timeouts** — `CONFIRMATION_TIMEOUT=0` and `PLAN_REVIEW_TIMEOUT=0` disable approval waits (Telegram `/yes` / `/no` and inline buttons)
- **Version** — package `Holix` 0.1.13 on PyPI

## 0.1.12 — 2026-06-12

### Added
- **Bootstrap web search** — optional search provider setup during `holix bootstrap` (`--skip-search`)
- **Telegram admin broadcast** — `/message all` and `/message PROFILE` with draft confirmation
- **Telegram inline access approval** — approve/reject buttons on admin notifications
- **curl installer** — locale-aware first-run bootstrap wizard
- **Yandex Webmaster** verification file `yandex_a50e5af9baf076d1.html` for holix-agent.ru

### Fixed
- **Gateway health check** — accept Hermes `{"status":"ok"}` on startup/reload (no false “not healthy”)
- **Gateway docs companion** — reload state before printing docs URL after `--with-docs`
- **Telegram profiles** — unlock approved users without interactive profile key; seed LLM settings from bot profile
- **Telegram isolation** — non-admins no longer see profile list; switch hidden profiles via `/profile name key`
- **Gateway SQLite paths** — API keys DB and profile memory DBs resolve under `HOLIX_HOME`
- **LTM SQLite** — prepare `ltm.db` and colocate paths with `memory.db`
- **Bootstrap on old CPUs** — pin `numpy<2.4` for Chromadb on x86 without AVX2
- **web-docs chat widget** — align DOM ids with `helix-chat-*` selectors

### Changed
- **Version** — package `Holix` 0.1.12 on PyPI

## 0.1.11 — 2026-06-11

### Changed
- **Rebrand Helix → Holix** — CLI command `holix`, PyPI package `Holix`, repo `javded-itres/Holix`
- Management API prefix `/api/holix/`; env vars `HOLIX_*`; data dir `~/.holix` (legacy `~/.helix` / `HELIX_HOME` supported)
- Project context file `.holix/HOLIX.md` (legacy `HELIX.md` still read)

### Added
- **Multi-profile gateway (v0.2)** — one uvicorn process, `ProfileAgentRegistry`, per-profile Telegram + cron companions
- **Hermes-compatible API** — `/v1/models`, `/v1/capabilities`, `/v1/responses`, `/v1/runs` (SSE), `/api/jobs`, `/api/sessions`; session header aliases `X-Holix-*` / `X-Hermes-*`
- **Holix Management API** — `/api/holix/` profiles, models, skills, MCP, config/env, global settings; profile key auth (`X-Holix-Profile-Key`)
- **Telegram admin API** — `/api/holix/profiles/{id}/telegram/*` (setup, requests approve/reject, admin, map, sync-menu)
- **`HOLIX_REQUIRE_AUTH=true`** by default — public without key: only `GET /health`, `GET /v1/health`
- **Profile identity** — `SOUL.md`, `USER.md`, `INIT.md` per profile; first-run onboarding with `save_agent_soul`, `save_user_profile`, `complete_agent_initialization`
- **SOUL injection** — pinned agent soul in every session and after context compression
- **Telegram admin** — single admin via `telegram requests approve --set-admin`; `telegram admin show|clear`
- **Telegram access flow** — admin notifications on `/start`; slash menu hidden until approve; `telegram sync-menu`

### Documentation
- **GATEWAY_API.md** (EN/RU) — **complete API reference** (~110 endpoints): auth, Swagger Authorize, Hermes, sessions, jobs, `/api/holix/`, admin, metrics, docs-chat; curl examples per section
- **GATEWAY.md** (EN/RU) — interactive `/docs`, API key bootstrap, metrics endpoints, bundled docs site
- **CLI.md**, **SECURITY.md**, **README** (EN/RU) — gateway API keys (`hx_` vs `hp_`), two-layer auth, docs-chat token
- **web-docs** — nav label "Complete API Reference" / "Полный справочник API", updated SEO for `gateway-api`
- **PROFILES**, **CONFIGURATION**, **USER_GUIDE**, **START_HERE**, **DOCTOR** (EN/RU) — agent identity files and onboarding
- **CHANGELOG** — unreleased features from `feature/telegram-profiles`

### Fixed
- **CI** — ruff, SOUL-related tests, Python 3.12 annotations, Linux port checks, Windows pytest/doctor encoding
- **`holix doctor --no-llm`** — skips live LLM endpoint probe (deterministic checks only)

## 0.1.8 — 2026-06-10

### Added
- **`holix telegram map`** — bind Telegram user id → Holix profile (`set`, `list`, `remove`, `bind`, `import`) for a shared bot
- Auto profile routing per Telegram chat from `telegram-users.json` / `HOLIX_TELEGRAM_USER_PROFILES`
- **TELEGRAM_MULTI_PROFILE** (EN/RU) — one bot vs multiple bots, isolation, mapping guide

### Documentation
- **CLI**, **CONFIGURATION**, **USER_GUIDE**, **TELEGRAM**, **PROFILES** (EN/RU) — `telegram map` and user→profile bindings
- **INSTALLATION** (EN/RU) — dedicated Windows section (PowerShell, data paths, typical workflow)
- **instruction.md** — quick reference at repo root

### Fixed
- **CI (ruff)** — auto-fix import/style across `core`, `cli`, `api`, `integrations`, `tests`; restore TUI re-exports and session rename handler
- **Telegram MCP remove picker** — stray profile-picker block removed from `_show_mcp_remove_picker`
- **Sub-agent tool guard** — pass `data_dir` into permission checks in subprocess
- **Tests** — isolated telegram vision settings; skill slug names in assignments test

## 0.1.7 — 2026-06-10

### Added
- **`holix profile whitelist`** — `add`, `list`, `enable` for per-profile terminal command whitelist
- **web-docs SEO** — per-page meta, `sitemap.xml`, `robots.txt`, clean `/docs/<slug>` URLs
- **Docs chat widget** — stable thinking indicator, auto-navigation to first doc link in reply
- **Yandex Webmaster** verification file at site root

### Documentation
- **TERMINAL_SECURITY** (EN/RU) — whitelist, dangerous patterns, confirmations, allowed/forbidden commands
- **EXECUTION_MODES** (EN/RU) — ReAct, Plan, Hybrid, Auto with prompt examples and plan approval flow
- **PROFILES**, **CLI**, **CONFIGURATION**, **SECURITY**, **DEPLOYMENT** (EN/RU) — whitelist CLI and site build/SEO

### Fixed
- **Docs sidebar** — `execution-modes` and `terminal-security` pages visible in navigation
- **Locale in LLM replies** — `/lang ru|en` forces all user-facing responses in the selected language (agent, plan steps, docs chat)

## 0.1.6 — 2026-06-09

### Documentation
- **Profiles & Isolation** (EN/RU) — per-profile `.env`, gateway, Telegram, workspace jail
- **Profile access keys** — optional protection for profile switching (`profile key`, `--protect`, `HOLIX_PROFILE_KEY`)
- **Telegram channel** [@helix_agent](https://t.me/helix_agent) linked in README and TELEGRAM guides
- **DEPLOYMENT** — per-profile gateway, systemd `holix-gateway@`, docs-server env vars
- **CONFIGURATION**, **CLI**, **GATEWAY**, **USER_GUIDE** updated for profiles and multi-gateway setup
- Donation link updated to Boosty

### Added
- **Per-profile isolation** — `.env`, gateway state/logs, Telegram bot, workspace jail per profile
- **Optional profile access keys** — off by default; opt-in via `profile create --protect` or `profile key init`
- **`holix profile`** — `env`, `jail`, `key status|init|rotate|disable`
- **`--no-verify-ssl`** on `holix models setup` and `holix models add` for self-signed/internal LLM endpoints
- Cross-session memory search tools (`search_session_memory`, `read_session_memory`)
- Telegram: send generated files to chat; paginated `/skills` picker
- Per-profile gateway deployment (`holix-gateway@.service`)

### Fixed
- Custom provider setup: `probe_provider is not defined`
- Gateway legacy state and orphan companion workers
- Context compression at 95% after tools and on session load
- Graph `max_steps` check before tool dispatch in plan mode
- Runtime data stored under profile dir instead of project CWD
- CLI hints omit `-p default` for active profile

## 0.1.5 — 2026-06-07

### Added
- **Yandex Metrika** on holix-agent.ru (counter 109712139, SPA page-view tracking)

### Security
- Path traversal fix for `GET /v1/plans/{plan_id}`
- Hide exception details in API/streaming unless `HOLIX_LOG_DEBUG`
- XSS hardening in web-docs SPA (slug validation, safe DOM rendering)
- API key hashing requires `HOLIX_API_KEY_PEPPER` (HMAC-SHA256 only)
- Strict URL hostname matching for provider presets and GitHub sources
- CI workflow: explicit `permissions: contents: read`

## 0.1.4 — 2026-06-07

### Added
- **web-docs** — marketing landing page (advantages, capabilities, use cases, Russian software emphasis)
- Separate **Documentation** tab with hub, sidebar navigation, and search

### Changed
- Site default language set to **Russian** (`ru`)
- Install guides and PyPI docs updated for `Holix`

## 0.1.3 — 2026-06-07

### Changed
- PyPI distribution renamed to **`Holix`**; Python **`>=3.12`**; heavy deps moved to extras (`browser`, `telegram`, `voice`, `tui-web`, `windows`, `all`)
- CI: Python 3.12/3.13/3.14 matrix, `build` job with `twine check` and wheel smoke install
- Publish workflow: build + publish jobs, tag `v*` trigger, Trusted Publishing (OIDC), smoke install before upload
- Documentation and web-docs: PyPI install as default path (`pipx install Holix`)

### Added
- **web-docs** — dark documentation site with search, EN/RU, mobile layout (`holix docs`)
- **Gateway docs companion** — optional `--with-docs` / `HOLIX_GATEWAY_WITH_DOCS`
- Auto-seed `~/.holix/.env` and `.env.example` on first `HOLIX_HOME` setup
- Hatch build hook for patch version bump on `uv build` (`HOLIX_NO_VERSION_BUMP=1` to disable)

### Security
- Shared permission manager, gateway auth hardening, SSRF checks, subagent API key via env, chat locking

### Fixed
- web-docs routing for in-page TOC anchors, home route (`#/`), mobile search and sidebar menu
