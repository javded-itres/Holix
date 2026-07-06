# Changelog

## Unreleased

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