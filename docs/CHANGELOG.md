# Changelog

## Unreleased

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
- **Telegram channel** [@holix_agent](https://t.me/holix_agent) linked in README and TELEGRAM guides
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