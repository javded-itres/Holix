# CLI reference

Entry point: **`helix`** (Typer). Every subcommand inherits global options unless noted.

## Global options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--profile` | `-p` | `default` | Active profile (`~/.helix/profiles/<name>/`) |
| `--verbose` | `-v` | off | Print profile and model on startup |

For **default** profile, omit `-p`:

```bash
helix gateway stop           # profile default
helix -p work status         # non-default profiles
helix --help
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
| `gateway` | API gateway supervisor |
| `cron` | Scheduled agent tasks (gateway scheduler) |
| `logs` | View, filter, rotate logs; debug mode |
| `doctor` | Diagnostics and `--fix` |
| `mcp` | Model Context Protocol servers |
| `hub` | External skill catalogs |
| `install` | Put `helix` on PATH (from repo) |
| `update` | Update installation |

Slash commands for TUI/Telegram: **[SLASH_COMMANDS.md](SLASH_COMMANDS.md)**.

---

## `helix chat-command`

Interactive REPL with history in `~/.helix/logs/history_<profile>.txt`.

```bash
helix chat-command
helix chat-command -m qwen2.5-coder:32b
helix chat-command --temperature 0.3 --max-steps 20
```

| Option | Description |
|--------|-------------|
| `--model`, `-m` | Override profile model |
| `--temperature`, `-t` | Sampling temperature |
| `--max-steps` | Max agent loop steps |

Built-in slash commands: `/help`, `/exit`, `/clear`, `/model`, `/profile`, `/skills`, `/memory`, `/status`, `/metrics`, `/stream`, `/debug`, `/compress`.  
Full list: [SLASH_COMMANDS.md](SLASH_COMMANDS.md#helix-chat-command-only).

---

## `helix run`

```bash
helix run "Summarize this repo"
helix run "Fix the test" -m smart -c my_conversation_id
```

| Argument / option | Description |
|-------------------|-------------|
| `query` | User message (required) |
| `--model`, `-m` | Model override |
| `--temperature`, `-t` | Temperature override |
| `--conversation-id`, `-c` | Conversation id (default `cli_oneshot`) |

---

## `helix tui`

Code-style terminal UI (default). Legacy dashboard: `HELIX_TUI_LEGACY=1 helix tui`.

```bash
helix tui
helix tui -p work
uv sync --extra tui-web
helix tui --web
helix tui --web --allow-lan --host 0.0.0.0 --port 8787 --token "$(openssl rand -hex 32)"
```

| Option | Description |
|--------|-------------|
| `--profile`, `-p` | Profile (also on global callback; TUI accepts its own) |
| `--web` | Serve UI in browser via textual-serve |
| `--host` | Bind address (`--web`) |
| `--port` | Port (`--web`, default `8787`) |
| `--public-url` | URL behind reverse proxy |
| `--token` | Shared secret (`HELIX_TUI_WEB_TOKEN`) |
| `--allow-lan` | Bind `0.0.0.0` (requires `--token`) |
| `--generate-token` / `--no-generate-token` | Ephemeral token on loopback |

Details: [TUI.md](TUI.md), slash: [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

---

## `helix status`

Shows active profile, model, `base_url`, temperature, max steps, data directory, and table of all profiles.

---

## `helix clear`

Deletes `data/` under the profile (memory DB, skills, security). Recreates empty dirs.

```bash
helix clear
helix clear -y
```

Use `-y` / `--yes` to skip confirmation. Extra caution on `default` profile.

---

## `helix version`

Prints package version and project metadata.

---

## `helix install`

Installs `helix` globally from detected repo root.

```bash
helix install
helix install --extra telegram --extra browser
helix install --system
helix install --no-path
helix install --repo /path/to/helix
```

| Option | Description |
|--------|-------------|
| `--system` | Install for all users |
| `--no-path` | Do not modify shell PATH |
| `--extra`, `-e` | Repeatable: `telegram`, `browser` |
| `--repo` | Source tree path |

See [INSTALLATION.md](INSTALLATION.md).

---

## `helix update`

```bash
helix update
helix update --check
helix update --channel auto|git|pypi
helix update --force
helix update --no-fetch
```

| Option | Description |
|--------|-------------|
| `--check`, `-n` | Check only, do not install |
| `--channel`, `-c` | `auto`, `git`, or `pypi` |
| `--repo` | Git repo path override |
| `--force`, `-f` | Reinstall even if up to date |
| `--no-fetch` | Skip `git fetch` (git channel) |

---

## `helix config`

Profile file: `~/.helix/profiles/<profile>/config.yaml`

| Subcommand | Description |
|------------|-------------|
| `show` | Dump current profile as YAML |
| `edit` | Open in `$EDITOR` (default `nano`) |
| `set <key> <value>` | Set a top-level `ProfileConfig` field |

```bash
helix config show
helix config edit
helix config set max_steps 25
```

Project supplements: `./.helix/skills`, `./.helix/plan`, local `config.yaml` merge (system keys ignored). See [CONFIGURATION.md](CONFIGURATION.md).

---

## `helix models`

| Subcommand | Description |
|------------|-------------|
| `setup` | Interactive wizard: providers, tests, `agent_models` |
| `list` | List configured providers |
| `agents` | Show per-agent model assignments |

```bash
helix models setup
helix models setup -p work
helix models list
helix models agents
```

Example `config.yaml` fragment:

```yaml
default_provider: litellm
providers:
  litellm:
    base_url: http://localhost:4000/v1
    api_key: ${LITELLM_KEY}
    default_model: smart
agent_models:
  main:
    provider: litellm
    model: smart
  code-reviewer:
    provider: litellm
    model: heavy
```

---

## `helix skills`

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
helix skills list
helix skills list --agent main
helix skills search "kubernetes"
helix skills assign my-skill --agents main,researcher
```

Hub-installed bundles live under `data/skills/_hub/` — see [HUB.md](HUB.md).

---

## `helix memory`

| Subcommand | Description |
|------------|-------------|
| `search <query>` | Semantic search in agent memory |

```bash
helix memory search "deployment nginx"
```

In TUI/chat use `/memory <query>`.

---

## `helix profile`

Per-profile isolation: env file and optional workspace jail.

| Subcommand | Description |
|------------|-------------|
| `env` | Show profile `.env` path and contents |
| `env --edit` | Open `profiles/<name>/.env` in `$EDITOR` |
| `jail enable <path>` | Restrict file/terminal tools to one directory |
| `jail disable` | Turn off workspace jail |
| `jail status` | Show jail settings |

```bash
helix -p alice profile env --edit
helix -p data-agent profile jail enable ~/data-agent
helix -p data-agent profile jail status
```

See [CONFIGURATION.md](CONFIGURATION.md#workspace-jail-optional).

---

## `helix gateway`

Background supervisor for FastAPI gateway (+ Telegram when configured). **Scoped to active profile** — multiple gateways can run on different ports.

| Subcommand | Description |
|------------|-------------|
| `start` | Start in background (default `127.0.0.1:8000`) |
| `stop` | Stop gateway and companions for this profile |
| `status` | Process and health for this profile |
| `reload` | Restart with same host/port/profile |

```bash
helix gateway start
helix gateway start -f          # foreground
helix gateway start --reload    # dev auto-reload
helix gateway status
helix gateway stop
helix gateway reload
# other profile: helix -p alice gateway start
```

State: `~/.helix/profiles/<profile>/gateway/state.json` · Logs: `profiles/<profile>/gateway/gateway.log`  
API details: [GATEWAY.md](GATEWAY.md).

---

## `helix cron`

Built-in scheduler (runs inside gateway supervisor). Jobs stored per profile.

| Subcommand | Description |
|------------|-------------|
| `list` | List jobs, next run, last status |
| `add "<schedule> :: <task>"` | Add job (`--name` optional) |
| `enable <id>` / `disable <id>` | Toggle job |
| `remove <id>` | Delete job |

```bash
helix gateway start
helix cron add "every day at 9 :: Summarize yesterday git log"
helix cron add "0 9 * * 1-5 :: Standup prep" --name standup
helix cron list
helix cron disable job-id
```

TUI/Telegram: `/cron`, `/cron add …`, `/cron bind <id>`.  
Run log: `~/.helix/profiles/<profile>/data/cron/runs.log` · Skill: bundled `helix-cron`.

---

## `helix logs`

Unified log viewer for agent, sub-agent, gateway, cron, and system logs.

| Subcommand | Description |
|------------|-------------|
| *(default)* / `show` | Recent lines (all sources) |
| `list` | Log files and sizes |
| `rotate` | Size-based rotation + purge old backups |
| `debug on` / `off` / `status` | Persisted debug mode |

```bash
helix logs
helix logs -n 200 -s agent -l error
helix logs -g "Tool call" -f
helix logs list
helix logs rotate
helix logs debug on
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

## `helix doctor`

| Option | Description |
|--------|-------------|
| `--fix` | Apply safe fixes + LLM repair of `config.yaml` |
| `--no-llm` | Deterministic checks/fixes only |
| `--no-advice` | Skip LLM remediation plan in check-only mode |

```bash
helix doctor
helix doctor --fix
helix doctor --no-llm
helix -p prod doctor
```

Checks: `~/.helix` writable, profile YAML, providers, hub lockfile, MCP env placeholders, skill assignments, gateway state, Telegram, platform (OS, PATH tools), production security.  
Details: [DOCTOR.md](DOCTOR.md).

---

## `helix mcp` {#mcp}

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
helix mcp setup
helix mcp list-popular
helix mcp install filesystem
helix mcp test my-server
```

Tools appear as `mcp_<server>_<toolname>` in the agent.  
In TUI: `/mcp` — [SLASH_COMMANDS.md](SLASH_COMMANDS.md#mcp-in-session).

---

## `helix hub`

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
helix hub browse
helix hub install clawhub:my-skill@1.0
helix hub install --agents main,coder
helix hub autoupdate --enable
```

Full guide: [HUB.md](HUB.md).

---

## `helix telegram`

Requires `uv sync --extra telegram`. Bot token is stored per profile in `profiles/<name>/telegram.env`.

| Subcommand | Description |
|------------|-------------|
| `setup` | Token, allowlist, save to profile |
| `run` | Start polling (`-p` selects profile) |
| `status` | Show saved config (token masked) |
| `sync-menu` | Push slash menu to Telegram |

```bash
helix -p alice telegram setup
helix -p alice telegram run
helix -p alice telegram sync-menu
```

Or start with gateway: `helix -p alice gateway start`.  
See [TELEGRAM.md](TELEGRAM.md).

---

## Profiles

| Path | Content |
|------|---------|
| `~/.helix/profiles/<name>/.env` | API keys, gateway port, feature flags |
| `~/.helix/profiles/<name>/telegram.env` | Telegram bot token and allowlist |
| `~/.helix/profiles/<name>/gateway/` | Gateway PID state and log |
| `~/.helix/profiles/<name>/config.yaml` | Models, MCP, hub, workspace jail |
| `.../data/memory/` | SQLite + ChromaDB |
| `.../data/skills/` | Skill files and hub bundles |
| `.../data/security/` | API keys DB (if used) |

Switch per invocation:

```bash
helix -p staging run "deploy checklist"
helix -p staging profile jail enable ~/staging-workspace
```

In TUI: `/profile <name>` or `/profile N`.

---

## Recommended workflows

| Goal | Commands |
|------|----------|
| Daily coding | `helix tui` |
| Scripting / CI | `helix run "…"` |
| Remote API | `helix gateway start` |
| Scheduled tasks | `helix gateway start` → `helix cron add "…"` |
| Debug failures | `helix logs -l error -f` |
| New machine | `helix install` → `helix doctor` → `helix models setup` |
| Skills from web | `helix hub browse` |
| MCP tools | `helix mcp setup` |

---

## See also

- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — all `/` commands
- [INSTALLATION.md](INSTALLATION.md) — install and update
- [CONFIGURATION.md](CONFIGURATION.md) — `.env` and YAML
- [LOGS.md](LOGS.md) — logging and `helix logs`
- [TUI.md](TUI.md) — terminal UI
- [HUB.md](HUB.md) — skill catalogs