# CLI reference

Entry point: **`holix`** (Typer). Every subcommand inherits global options unless noted.

## Global options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--profile` | `-p` | *(dev: `default`)* | Active profile (`~/.holix/profiles/<name>/`) |
| `--profile-key` | | env `HOLIX_PROFILE_KEY` | Access key for a protected profile |
| `--verbose` | `-v` | off | Print profile and model on startup |

In **development**, omit `-p` to use profile `default`. In **production** (`HOLIX_ENV=production`), `-p` with a **named** profile is required — `default` is not available:

```bash
holix gateway stop                    # dev: profile default
holix -p work status
HOLIX_ENV=production holix -p shared gateway start
holix --help
```

---

## Top-level commands

| Command | Purpose |
|---------|---------|
| `chat-command` | Interactive terminal chat (prompt_toolkit) |
| `run` | One-shot query, then exit |
| `tui` | Full-screen Textual UI (recommended) |
| `status` | Profile, model, paths |
| `clear` | Wipe profile `data/` (memory, skills, security) |
| `version` | Version and license info |
| `skills` | Skill files and agent assignments |
| `memory` | Search stored memory |
| `config` | View/edit profile YAML |
| `profile` | Profile `.env` and workspace jail |
| `models` | Providers and `agent_models` routing |
| `telegram` | Telegram bot setup and run |
| `max` | MAX messenger bot setup and run |
| `gateway` | API gateway supervisor |
| `cron` | Scheduled agent tasks (gateway scheduler) |
| `logs` | View, filter, rotate logs; debug mode |
| `doctor` | Diagnostics and `--fix` |
| `mcp` | Model Context Protocol servers |
| `hub` | External skill catalogs |
| `launch` | External coding CLIs in tmux (Claude Code, OpenCode, Grok Build, …) |
| `install` | Put `holix` on PATH (from repo) |
| `update` | Update installation |

Slash commands for TUI/Telegram: **[SLASH_COMMANDS.md](SLASH_COMMANDS.md)**.

---

## `holix chat-command`

Interactive REPL with history in `~/.holix/logs/history_<profile>.txt`.

```bash
holix chat-command
holix chat-command -m qwen2.5-coder:32b
holix chat-command --temperature 0.3 --max-steps 20
```

| Option | Description |
|--------|-------------|
| `--model`, `-m` | Override profile model |
| `--temperature`, `-t` | Sampling temperature |
| `--max-steps` | Max agent loop steps |

Built-in slash commands: `/help`, `/exit`, `/clear`, `/model`, `/profile`, `/skills`, `/memory`, `/status`, `/metrics`, `/stream`, `/debug`, `/compress`.  
Full list: [SLASH_COMMANDS.md](SLASH_COMMANDS.md#holix-chat-command-only).

---

## `holix run`

```bash
holix run "Summarize this repo"
holix run "Fix the test" -m smart -c my_conversation_id
```

| Argument / option | Description |
|-------------------|-------------|
| `query` | User message (required) |
| `--model`, `-m` | Model override |
| `--temperature`, `-t` | Temperature override |
| `--conversation-id`, `-c` | Conversation id (default `cli_oneshot`) |

---

## `holix tui`

Code-style terminal UI.

```bash
holix tui
holix tui -p work
uv sync --extra tui-web
holix tui --web
holix tui --web --allow-lan --host 0.0.0.0 --port 8787 --token "$(openssl rand -hex 32)"
```

| Option | Description |
|--------|-------------|
| `--profile`, `-p` | Profile (also on global callback; TUI accepts its own) |
| `--web` | Serve UI in browser via textual-serve |
| `--host` | Bind address (`--web`) |
| `--port` | Port (`--web`, default `8787`) |
| `--public-url` | URL behind reverse proxy |
| `--token` | Shared secret (`HOLIX_TUI_WEB_TOKEN`) |
| `--allow-lan` | Bind `0.0.0.0` (requires `--token`) |
| `--generate-token` / `--no-generate-token` | Ephemeral token on loopback |

Details: [TUI.md](TUI.md), slash: [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

---

## `holix status`

Shows active profile, model, `base_url`, temperature, max steps, data directory, and table of all profiles.

---

## `holix clear`

Deletes `data/` under the profile (memory DB, skills, security). Recreates empty dirs.

```bash
holix clear
holix clear -y
```

Use `-y` / `--yes` to skip confirmation. Extra caution on `default` profile.

---

## `holix version`

Prints package version and project metadata.

---

## `holix install`

Installs `holix` globally from detected repo root.

```bash
holix install
holix install --extra telegram --extra browser
holix install --system
holix install --no-path
holix install --repo /path/to/Holix
```

| Option | Description |
|--------|-------------|
| `--system` | Install for all users |
| `--no-path` | Do not modify shell PATH |
| `--extra`, `-e` | Repeatable: `telegram`, `browser` |
| `--repo` | Source tree path |

See [INSTALLATION.md](INSTALLATION.md).

---

## `holix bootstrap`

First-run wizard after install: detect or choose UI language (RU/EN), configure LLM provider, optional Telegram bot + admin ID. Called automatically by `install.sh`.

```bash
holix bootstrap
holix bootstrap --lang ru
holix bootstrap --skip-telegram
holix bootstrap -y
```

| Option | Description |
|--------|-------------|
| `--lang` | UI language for setup (`en` \| `ru`); Russian OS locale skips the prompt |
| `--skip-llm` | Skip LLM provider setup |
| `--skip-telegram` | Skip Telegram wizard |
| `-y`, `--yes` | Non-interactive (skip prompts) |
| `-p`, `--profile` | Holix profile (default: `default`) |

Sets `profiles/default/data/locale.json` and `profiles/admin/data/locale.json`. See [INSTALLATION.md](INSTALLATION.md#one-line-install-curl).

---

## `holix update`

```bash
holix update
holix update --check
holix update --channel auto|git|pypi
holix update --force
holix update --no-fetch
```

| Option | Description |
|--------|-------------|
| `--check`, `-n` | Check only, do not install |
| `--channel`, `-c` | `auto`, `git`, or `pypi` |
| `--repo` | Git repo path override |
| `--force`, `-f` | Reinstall even if up to date |
| `--no-fetch` | Skip `git fetch` (git channel) |

---

## `holix config`

Profile file: `~/.holix/profiles/<profile>/config.yaml`

| Subcommand | Description |
|------------|-------------|
| `show` | Dump current profile as YAML |
| `edit` | Open in `$EDITOR` (default `nano`) |
| `set <key> <value>` | Set a top-level `ProfileConfig` field |

```bash
holix config show
holix config edit
holix config set max_steps 25
```

Project supplements: `./.holix/skills`, `./.holix/plans`, local `config.yaml` merge (system keys ignored). See [CONFIGURATION.md](CONFIGURATION.md).

---

## `holix models`

| Subcommand | Description |
|------------|-------------|
| `setup` | Interactive wizard: providers, tests, `agent_models`, fallbacks |
| `list` | List configured providers |
| `agents` | Show per-agent model assignments |
| `fallback list` | Show effective fallback chain |
| `fallback set PROVIDERS` | Set profile fallbacks (`litellm,ollama`) |
| `fallback clear` | Remove profile fallbacks |

```bash
holix models setup
holix models fallback set litellm,ollama
holix models fallback list
holix models list
```

Example `config.yaml` fragment:

```yaml
default_provider: litellm
fallback_providers:
  - ollama
providers:
  litellm:
    base_url: http://localhost:4000/v1
    api_key: ${LITELLM_KEY}
    default_model: smart
    fallback_providers:
      - openrouter
agent_models:
  main:
    provider: litellm
    model: smart
  code-reviewer:
    provider: litellm
    model: heavy
```

---

## `holix skills`

Skills are markdown with YAML frontmatter under `{profile}/data/skills/`, indexed in ChromaDB.

| Subcommand | Description |
|------------|-------------|
| `list` | List skills (`--agent` filters by assignment) |
| `search <query>` | Semantic search |
| `show <name>` | Full skill body |
| `assign <skill> --agents main,coder` | Update `skill_assignments` in profile |
| `unassign <skill> --agent coder` | Remove from allowlist |
| `agents <skill>` | Which agents may use the skill |
| `assign-wizard` | Interactive assignment UI |

```bash
holix skills list
holix skills list --agent main
holix skills search "kubernetes"
holix skills assign my-skill --agents main,researcher
```

Hub-installed bundles live under `data/skills/_hub/` — see [HUB.md](HUB.md).

---

## `holix memory`

| Subcommand | Description |
|------------|-------------|
| `search <query>` | Semantic search in agent memory |

```bash
holix memory search "deployment nginx"
```

In TUI/chat use `/memory <query>`.

---

## `holix profile`

Per-profile isolation plus **shared global settings** inherited by default.

| Subcommand | Description |
|------------|-------------|
| `create <name>` | New profile (`--inherit` default, `--clean` for standalone) |
| `create <name> --protect` | Create with access key + workspace jail |
| `global show` | Show `~/.holix/global/config.yaml` |
| `global edit` | Edit global YAML (models, MCP, behavior) |
| `global edit --env` | Edit `~/.holix/global/.env` |
| `global init` | (Re)create global config (`--from-profile default`) |
| `env` | Show profile `.env` path and contents |
| `env --edit` | Open profile overrides in `$EDITOR` |
| `jail enable <path>` | Restrict file/terminal tools to one directory |
| `jail disable` | Turn off workspace jail |
| `jail status` | Show jail settings |
| `whitelist add "<cmds>"` | Add comma-separated terminal commands |
| `whitelist list` | Show whitelist status and effective commands |
| `whitelist enable` | Enable terminal whitelist enforcement |
| `delete [name]` | Delete profile after notifying mapped Telegram users |
| `crypto …` | Encrypt profile secrets at rest (see below) |

```bash
holix profile global edit
holix profile create team-a
holix profile create team-b --clean
holix -p alice profile env --edit
holix -p data-agent profile jail enable ~/data-agent
holix -p shared profile delete ivan --yes
```

`profile delete` options: `--yes` / `-y` (skip confirmation), `--skip-notify` (no Telegram message). Protected profiles: `default`, `docs`, `global`.

### `holix profile crypto`

Encrypts **profile secrets** (`.env`, `telegram.env`, `SOUL.md`, memory DBs). **Workspace stays plaintext** for git-friendly project files.

| Subcommand | Description |
|------------|-------------|
| `enable` | Enable encryption for active profile |
| `migrate --all` | Bulk-enable on unencrypted profiles |
| `status` | Show encryption policy and unlock state |
| `unlock` | Unlock encrypted data for this CLI process |
| `lock` | Clear in-process unlock |
| `seal` / `seal --all` | Re-encrypt plaintext secrets after unlock |
| `decrypt-workspace` | One-time migration: legacy encrypted workspace → plaintext |
| `decrypt-workspace --all` | Migrate all profiles |
| `purge-cache` | Clear stale runtime decryption cache |

```bash
holix -p alice profile crypto enable
holix profile crypto migrate --all --yes
holix -p alice profile crypto decrypt-workspace --all --yes
holix -p alice profile crypto status
```

Gateway/systemd: set `HOLIX_UNLOCK_KEY` in profile or `global/.env` so the worker can read encrypted `telegram.env` and memory on startup.

See [CONFIGURATION.md](CONFIGURATION.md#profile-encryption-optional) and [PROFILES.md](PROFILES.md).

---

## `holix gateway`

Background supervisor for FastAPI gateway (+ Telegram when configured). **Scoped to active profile** — multiple gateways can run on different ports.

| Subcommand | Description |
|------------|-------------|
| `start` | Start in background (default `127.0.0.1:8000`) |
| `stop` | Stop gateway and companions for this profile |
| `status` | Process and health for this profile |
| `reload` | Restart with same host/port/profile |

```bash
holix gateway start
holix gateway start -f          # foreground
holix gateway start --reload    # dev auto-reload
holix gateway status
holix gateway stop
holix gateway reload
# other profile: holix -p alice gateway start
```

State: `~/.holix/profiles/<profile>/gateway/state.json` · Logs: `profiles/<profile>/gateway/gateway.log`  
API details: [GATEWAY.md](GATEWAY.md).

### Gateway API keys

There is **no** `holix` CLI command for creating gateway API keys (`hx_…`) yet. Use one of:

```bash
# curl (requires an existing admin hx_ key)
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys?name=my-app&permissions=read,write" \
  -H "Authorization: Bearer hx_admin_…"

# or Swagger UI after holix gateway start
open http://127.0.0.1:8000/docs   # Authorize → HolixApiKey → paste hx_…
```

**Profile access keys** (`hp_…`) are different — they protect profile switching and `/api/holix/*` management, not the gateway HTTP surface:

```bash
holix -p alice profile key init    # generates hp_… (shown once)
holix -p alice --profile-key hp_…  # use on CLI/TUI
```

First admin key bootstrap: temporarily set `HOLIX_REQUIRE_AUTH=false`, create via `POST /admin/api-keys`, then re-enable auth. Full endpoint reference: [GATEWAY_API.md](GATEWAY_API.md).

---

## `holix docs`

Documentation website (marketing landing + docs SPA, search, EN/RU).

| Subcommand | Description |
|------------|-------------|
| *(default)* | Serve site on `127.0.0.1:8080` |
| `serve` | Same as default |
| `build` | Sync `docs/en` + `docs/ru` → `web-docs/`, rebuild search index and SEO artifacts |

```bash
holix docs build
holix docs --port 8080 --open
holix gateway start --with-docs
```

See [DEPLOYMENT.md](DEPLOYMENT.md#documentation-site-build-and-seo).

---

## `holix cron`

Built-in scheduler (runs inside gateway supervisor). Jobs stored per profile.

| Subcommand | Description |
|------------|-------------|
| `list` | List jobs, next run, last status |
| `add "<schedule> :: <task>"` | Add job (`--name` optional) |
| `enable <id>` / `disable <id>` | Toggle job |
| `remove <id>` | Delete job |

```bash
holix gateway start
holix cron add "every day at 9 :: Summarize yesterday git log"
holix cron add "0 9 * * 1-5 :: Standup prep" --name standup
holix cron list
holix cron disable job-id
```

TUI/Telegram/MAX: `/cron`, `/cron add …`, `/cron bind <id>`.  
**Auto-create (0.1.16+):** recurring natural-language chat (RU/EN) creates jobs without `/cron add` — see [CRON.md](CRON.md).  
Run log: `~/.holix/profiles/<profile>/data/cron/runs.log` · Skill: bundled `holix-cron`.

---

## `holix logs`

Unified log viewer for agent, sub-agent, gateway, cron, and system logs.

| Subcommand | Description |
|------------|-------------|
| *(default)* / `show` | Recent lines (all sources) |
| `list` | Log files and sizes |
| `rotate` | Size-based rotation + purge old backups |
| `debug on` / `off` / `status` | Persisted debug mode |

```bash
holix logs
holix logs -n 200 -s agent -l error
holix logs -g "Tool call" -f
holix logs list
holix logs rotate
holix logs debug on
```

| Option | Description |
|--------|-------------|
| `-n`, `--lines` | Number of lines (default 80) |
| `-s`, `--source` | `all`, `agent`, `gateway`, `cron`, `subagent`, `system` |
| `-l`, `--level` | Minimum level: `debug`, `info`, `warning`, `error` |
| `-g`, `--grep` | Substring filter |
| `-f`, `--follow` | Stream new lines |
| `--debug` | Include `agent.debug.jsonl` |
| `-v`, `--verbose` | Show extra JSON fields |

Full guide: [LOGS.md](LOGS.md).

---

## `holix doctor`

| Option | Description |
|--------|-------------|
| `--fix` | Apply safe fixes + LLM repair of `config.yaml` |
| `--no-llm` | Deterministic checks/fixes only |
| `--no-advice` | Skip LLM remediation plan in check-only mode |

```bash
holix doctor
holix doctor --fix
holix doctor --no-llm
holix -p prod doctor
```

Checks: `~/.holix` writable, profile YAML, providers, hub lockfile, MCP env placeholders, skill assignments, gateway state, Telegram, platform (OS, PATH tools), production security.  
Details: [DOCTOR.md](DOCTOR.md).

---

## `holix mcp` {#mcp}

Configure MCP servers in profile `mcp_servers` / `mcp_assignments`.

| Subcommand | Description |
|------------|-------------|
| `list` | Configured servers |
| `add [name]` | Manual stdio/SSE server wizard |
| `remove [name]` | Remove server |
| `test <name>` | Connect and list tools |
| `assign` | Interactive assign to agents |
| `setup` | Add servers + assign wizard |
| `list-popular` | Curated install list |
| `install` | From popular list or git URL |

```bash
holix mcp setup
holix mcp list-popular
holix mcp install filesystem
holix mcp test my-server
```

Tools appear as `mcp_<server>_<toolname>` in the agent.  
In TUI: `/mcp` — [SLASH_COMMANDS.md](SLASH_COMMANDS.md#mcp-in-session).

---

## `holix hub`

| Subcommand | Description |
|------------|-------------|
| `search <query>` | Search catalogs (`-s clawhub`, `skills-sh`, `hermes`, …) |
| `marketplaces` | Claude Code marketplaces |
| `plugins` | Plugins in a marketplace |
| `browse` | Interactive install |
| `install <spec>` | Install skill or plugin |
| `list` | Hub-installed entries |
| `remove <id>` | Remove bundle + lockfile |
| `check-updates` | ClawHub version bumps |
| `update` | Reinstall from `hub-lock.json` |
| `autoupdate` | Enable scheduled updates |
| `slash-sync` | Rebuild `skill-slash.json` |

```bash
holix hub browse
holix hub install clawhub:my-skill@1.0
holix hub install --agents main,coder
holix hub autoupdate --enable
```

Full guide: [HUB.md](HUB.md).

---

## `holix telegram`

Requires `aiogram` — from source: `uv sync --extra telegram`; with `uv tool install`: `uv tool install . --force --with aiogram --with pypdf`. Bot token is stored per profile in `profiles/<name>/telegram.env` (often encrypted). Do not leave an empty `TELEGRAM_BOT_TOKEN=` in `global/.env` — omit the key or Holix loads the token from `telegram.env`.

| Subcommand | Description |
|------------|-------------|
| `setup` | Wizard: bot token only; enables access-request mode |
| `run` | Start polling (`-p` selects bot host profile) |
| `status` | Saved config (token masked) and bindings |
| `sync-menu` | Push slash menu to **authorized** users only (hidden until approve) |
| `admin show` | Show the single Telegram admin (CLI-assigned) |
| `admin clear` | Clear admin before reassigning (`--set-admin` on approve) |
| `requests list` | Pending `/start` access requests |
| `requests approve USER_ID` | Approve user (`--create-profile`, `--profile`, `-i`, or `--set-admin`) |
| `requests reject USER_ID` | Reject a pending request |
| `map set USER_ID PROFILE` | Manual bind Telegram user id → Holix profile |
| `map list` | List bindings |
| `map remove USER_ID` | Remove a binding |
| `map bind PROFILE` | Quick bind (`--user-id` or id from allowlist) |
| `map import "ID:prof,..."` | Import multiple bindings |

```bash
holix -p shared telegram setup
holix -p shared telegram requests approve 123456789 --set-admin   # first admin + profile admin
holix -p shared telegram requests list
holix -p shared telegram requests approve 123456789 --create-profile ivan
holix -p shared telegram admin show
holix -p shared telegram map set 123456789 alice   # manual alternative
holix -p shared gateway start
```

Shared bot with isolated profiles: [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).  
See also [TELEGRAM.md](TELEGRAM.md).

---

## `holix max`

Requires `uv sync --extra max` and `MAX_ACCESS_TOKEN`.

| Subcommand | Description |
|------------|-------------|
| `setup` | Token, allowlist, webhook/polling mode, save config |
| *(default)* | Start Long Polling (dev/test) |
| `status` | `GET /me`, webhook subscriptions |

```bash
holix max setup
holix max
holix max status
```

Production: `holix gateway start` (webhook via `POST /subscriptions`).  
See [MAX.md](MAX.md).

---

## `holix launch`

Launch external coding agents in **tmux** with models from the active Holix profile. **Linux and macOS only.**

Full guide: **[LAUNCH.md](LAUNCH.md)**.

| Subcommand | Description |
|------------|-------------|
| `setup` | Interactive install and per-profile CLI bindings |
| `list` | Supported CLIs and binding status |
| `sessions` | Holix-managed tmux sessions |
| `tmux` | All tmux sessions on the host |
| `attach` | Attach to session by id or tmux name |
| `send` | Send prompt to running session |
| `chat` | Interactive relay (text + arrow keys) |
| `output` | Capture pane output |
| `kill` | Stop session |
| `<cli_id>` | Open agent (`claude`, `opencode`, `grok-build`, `gigacode`, `aider`) |
| `<cli_id> status` | Binding, model, env, active sessions |

```bash
holix launch setup
holix launch claude
holix launch opencode -t "fix tests" --detach
holix launch grok-build status
holix launch chat <session_id>
```

Per-agent options: `--cwd`, `--task` / `-t`, `--model-slot`, `--detach`, `--new`, `--window`, `--session`.

Supported CLIs and model mapping (OpenCode `OPENCODE_CONFIG`, Grok `GROK_HOME`, Claude gateway env): see [LAUNCH.md](LAUNCH.md).

---

## Profiles

| Path | Content |
|------|---------|
| `~/.holix/profiles/<name>/.env` | API keys, gateway port, feature flags |
| `~/.holix/profiles/<name>/telegram.env` | Bot token, allowlist, `HOLIX_TELEGRAM_USER_PROFILES` |
| `~/.holix/profiles/<name>/telegram-users.json` | Telegram user id → profile bindings (shared bot) |
| `~/.holix/profiles/<name>/gateway/` | Gateway PID state and log |
| `~/.holix/profiles/<name>/config.yaml` | Models, MCP, hub, workspace jail |
| `~/.holix/profiles/<name>/SOUL.md` | Agent personality (injected each session) |
| `~/.holix/profiles/<name>/USER.md` | User facts and preferences |
| `~/.holix/profiles/<name>/INIT.md` | First-run onboarding marker |
| `.../data/memory/` | SQLite + ChromaDB |
| `.../data/skills/` | Skill files and hub bundles |
| `.../data/security/` | API keys DB (if used) |
| `.../external_clis/` | External CLI bindings and launch sessions |
| `.../opencode/opencode.json` | Generated OpenCode provider config |
| `.../grok/config.toml` | Generated Grok Build model config |

Switch per invocation:

```bash
holix -p staging run "deploy checklist"
holix -p staging profile jail enable ~/staging-workspace
```

In TUI: `/profile <name>` or `/profile N`.

---

## Recommended workflows

| Goal | Commands |
|------|----------|
| Daily coding | `holix tui` |
| Scripting / CI | `holix run "…"` |
| Remote API | `holix gateway start` |
| Scheduled tasks | `holix gateway start` → `holix cron add "…"` |
| Debug failures | `holix logs -l error -f` |
| New machine | `holix install` → `holix doctor` → `holix models setup` |
| Skills from web | `holix hub browse` |
| MCP tools | `holix mcp setup` |
| External coding CLI | `holix launch setup` → `holix launch claude` |

---

## See also

- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — all `/` commands
- [INSTALLATION.md](INSTALLATION.md) — install and update
- [CONFIGURATION.md](CONFIGURATION.md) — `.env` and YAML
- [LOGS.md](LOGS.md) — logging and `holix logs`
- [TUI.md](TUI.md) — terminal UI
- [HUB.md](HUB.md) — skill catalogs
- [LAUNCH.md](LAUNCH.md) — external coding CLIs in tmux