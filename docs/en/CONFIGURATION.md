# Configuration

## Layers

1. **Shell environment** — highest priority (never overwritten by files)
2. **Profile `.env`** — `~/.holix/profiles/<name>/.env` (overrides only)
3. **Global `.env`** — `~/.holix/global/.env` (shared API keys, voice, tool flags)
4. **Legacy global `.env`** — `~/.holix/.env` (fallback when `global/.env` is missing)
5. **Project `.env`** — `./.env` in CWD (dev convenience)
6. **Profile YAML** — `~/.holix/profiles/<name>/config.yaml` (per-profile overrides)
7. **Global YAML** — `~/.holix/global/config.yaml` (shared models, MCP, behavior)
8. **CLI flags** — overrides per command

**Inheritance:** profiles created with `--inherit` (default) load global settings first; anything set in the profile file overrides global. Change global once → all inheriting profiles pick it up on next start (for keys not overridden in the profile).

```bash
holix profile global edit              # shared models, MCP, behavior
holix profile global edit --env        # shared env (Whisper, gateway defaults, …)
holix -p alice profile env --edit      # profile-only overrides
holix profile create bob               # inherits global (default)
holix profile create carol --clean     # standalone profile, manual setup
```

## Data directory (`HOLIX_HOME`)

| OS | Default |
|----|---------|
| Linux / macOS | `~/.holix` |
| Windows | `%LOCALAPPDATA%\Holix` |
| Override | `HOLIX_HOME` |
| Linux (XDG) | `$XDG_DATA_HOME/holix` |

Shared under `HOLIX_HOME`: `global/` (shared settings), logs, MCP server clones. **Per profile** under `profiles/<name>/`: `.env`, `config.yaml`, `telegram.env`, `gateway/`, `data/`.

### Global layout

| Path | Content |
|------|---------|
| `global/config.yaml` | Shared models, providers, MCP, search, agent behavior |
| `global/.env` | Shared API keys, Whisper/voice, gateway defaults, tool flags |

Initialized on first run (seeded from `profiles/default/config.yaml` when present, else built-in defaults). Manage with `holix profile global show|edit|init`.

### Profile layout

| Path | Content |
|------|---------|
| `profiles/<name>/.env` | Overrides only (unset keys inherit from `global/.env`) |
| `profiles/<name>/telegram.env` | Bot token, allowlist, `HOLIX_TELEGRAM_USER_PROFILES` |
| `profiles/<name>/telegram-users.json` | Telegram user id → Holix profile bindings |
| `profiles/<name>/gateway/state.json` | Running gateway PID and bind |
| `profiles/<name>/config.yaml` | Overrides only (inherits `global/config.yaml`) |
| `profiles/<name>/SOUL.md` | Agent personality (injected every session) |
| `profiles/<name>/USER.md` | User facts and preferences |
| `profiles/<name>/INIT.md` | First-run onboarding marker (removed after `complete_agent_initialization`) |
| `profiles/<name>/data/` | Memory, skills, security, cron |
| `profiles/<name>/workspace/` | Agent workspace (plaintext; not encrypted) |

### `telegram.env` loading

Holix loads `profiles/<bot-host>/telegram.env` after profile bootstrap and unlock. Values from this file **override empty** shell/global entries (e.g. blank `TELEGRAM_BOT_TOKEN=`). Encrypted files require `HOLIX_UNLOCK_KEY` in the environment or an active `holix profile crypto unlock` session.

## Profile encryption (optional)

Holix encrypts **profile secrets at rest**: `.env`, `telegram.env`, `SOUL.md`, `USER.md`, memory databases. **Workspace files stay plaintext** (git-friendly). Legacy encrypted workspace trees are migrated once with `holix profile crypto decrypt-workspace`.

```bash
holix -p alice profile crypto enable           # one profile
holix profile crypto migrate --all --yes       # bulk on existing installs
holix -p alice profile crypto unlock         # decrypt for this CLI session
holix profile crypto decrypt-workspace --all --yes   # workspace migration
holix -p alice profile crypto status
```

| Variable | Purpose |
|----------|---------|
| `HOLIX_UNLOCK_KEY` | User key for gateway/systemd to unlock encrypted profiles at startup |
| `HOLIX_ENCRYPTION_MODE` | Policy label (`linux-production`, etc.) |

Delivered files (Telegram attachments) are materialized as plaintext before send when encryption is enabled.

Full guide (OS policy, threat model, gateway unlock): [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md).  
See also [SECURITY.md](SECURITY.md#encryption-at-rest) and `holix profile crypto --help`.

## Workspace jail (optional)

Restrict file and terminal tools to one directory tree — useful when several people share one machine with separate profiles.

```bash
holix -p data-agent profile jail enable ~/data-agent
holix -p data-agent profile jail status
holix -p data-agent profile jail disable
```

Or in `config.yaml`:

```yaml
workspace_jail_enabled: true
workspace_root: /home/user/data-agent
```

When enabled, `read_file`, `write_file`, `list_directory`, `run_terminal_command`, and Telegram file delivery cannot access paths outside `workspace_root`.

## Terminal whitelist (optional)

Restrict which shell commands the agent may run. Managed per profile:

```bash
holix -p dev profile whitelist enable
holix -p dev profile whitelist add "ls, cat, python, git"
holix -p dev profile whitelist list
```

Equivalent `.env` variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOLIX_TERMINAL_COMMAND_WHITELIST` | `true` | Enforce whitelist for `run_terminal_command` |
| `HOLIX_TERMINAL_WHITELIST_EXTRA` | empty | Comma-separated extra commands or prefixes |

Platform defaults are always included. See [SECURITY.md](SECURITY.md).

## Telegram (shared bot, multiple users)

**Recommended** — access requests (`holix telegram setup` enables this by default):

```bash
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

**Manual** bindings when one bot serves several Holix profiles:

```bash
holix -p shared telegram map set 123456789 alice
holix -p shared telegram map import "111:alice,222:bob"
```

| Variable / file | Description |
|-----------------|-------------|
| `HOLIX_TELEGRAM_ACCESS_REQUESTS` | `true` — users send `/start`, admin approves via CLI (default after `telegram setup`) |
| `HOLIX_TELEGRAM_ADMIN_USER_ID` | Single Telegram admin user id (set via `requests approve --set-admin`; CLI only) |
| `HOLIX_TELEGRAM_ADMIN_PROFILE` | Holix profile for the admin (default: `admin`) |
| `telegram-access-requests.json` | Pending/resolved access requests per bot profile |
| `HOLIX_TELEGRAM_ALLOWED_USERS` | Manual allowlist (optional when access requests are on) |
| `HOLIX_TELEGRAM_USER_PROFILES` | `USER_ID:profile` comma-separated in `telegram.env` |
| `telegram-users.json` | User bindings; updated by `map` or `requests approve` |

Details: [TELEGRAM.md](TELEGRAM.md) (incl. multi-profile topologies).

## Key environment variables

See [.env.example](../../.env.example).

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `HOLIX_LOG_LEVEL` | `INFO` | Root log level (`LOG_LEVEL` alias) |
| `HOLIX_LOG_DEBUG` | `false` | Enable debug log file (`LOG_DEBUG` alias) |
| `HOLIX_LOG_MAX_BYTES` | `10485760` | Rotate when file exceeds size (bytes) |
| `HOLIX_LOG_BACKUP_COUNT` | `10` | Rotating backup files to keep |
| `HOLIX_LOG_ROTATION_DAYS` | `14` | Purge backups older than N days |

CLI: `holix logs debug on|off` persists to `logs/logging.json`.  
Details: [LOGS.md](LOGS.md).

## Profile secrets

```yaml
api_key: ${OPENAI_API_KEY}
providers:
  openai:
    api_key: ${ENV:OPENAI_API_KEY}
```

## Models

```bash
holix models presets          # OpenAI, OpenRouter, DeepSeek, Kimi, Grok, Groq, …
holix models add openrouter   # quick add from catalog
holix models add ollama --host 192.168.1.10:11434
holix models add litellm --host http://proxy.local:4000
holix models add vllm --host gpu-node:8000
holix models setup            # interactive wizard (prompts for host on local presets)
holix models list
```

### Provider catalog

| Preset ID | Service | API key env | Auth notes |
|-----------|---------|-------------|------------|
| `openai` | OpenAI | `OPENAI_API_KEY` | Bearer |
| `openrouter` | OpenRouter (multi-vendor) | `OPENROUTER_API_KEY` | + `HTTP-Referer`, `X-Title` headers |
| `anthropic` | Claude via OpenRouter | `OPENROUTER_API_KEY` | Native Anthropic API is not OpenAI-compatible |
| `deepseek` | DeepSeek | `DEEPSEEK_API_KEY` | Bearer |
| `moonshot` | Kimi / Moonshot | `MOONSHOT_API_KEY` | Bearer |
| `xai` | Grok | `XAI_API_KEY` | Bearer |
| `groq` | Groq | `GROQ_API_KEY` | Bearer |
| `google` | Gemini (OpenAI-compat endpoint) | `GOOGLE_API_KEY` | Bearer |
| `ollama` | Local Ollama | (any / `ollama`) | No key; configurable host |
| `litellm` | Local LiteLLM proxy | `LITELLM_API_KEY` | Unified proxy; configurable host |
| `vllm` | vLLM OpenAI server | (often `EMPTY`) | Local/remote GPU; configurable host |

### Host for Ollama, LiteLLM, vLLM

These presets use an OpenAI-compatible `base_url` built from host + port (default ports: **11434**, **4000**, **8000**).

| Preset | Env variable | Default |
|--------|--------------|---------|
| `ollama` | `OLLAMA_HOST` | `http://127.0.0.1:11434/v1` |
| `litellm` | `LITELLM_API_BASE` | `http://127.0.0.1:4000/v1` |
| `vllm` | `VLLM_HOST` | `http://127.0.0.1:8000/v1` |

Host values accept:

- hostname only (`gpu-server` → `http://gpu-server:<default_port>/v1`)
- `host:port` (`192.168.1.5:11434`)
- full URL (`http://nas:11434` or `http://nas:11434/v1`)

CLI: `--host` and optional `--port` on `holix models add`. Wizard and `add` read env vars when set (see [.env.example](../../.env.example)).

Example profile fragment:

```yaml
default_provider: openrouter
providers:
  openrouter:
    base_url: https://openrouter.ai/api/v1
    api_key: ${OPENROUTER_API_KEY}
    default_model: anthropic/claude-sonnet-4
    metadata:
      auth_type: openrouter
      preset_id: openrouter
      http_referer: ${OPENROUTER_HTTP_REFERER}
      x_title: Holix
```

Legacy top-level fields (`model`, `base_url`) still work; prefer `providers` + `default_provider`.

### Provider fallback (when LLM is unavailable)

If the primary provider fails (connection error, timeout, rate limit, model not found), Holix tries **fallback providers** in order and switches the active client for the rest of the session step.

**Profile-level** (applies to all agents using the default provider chain):

```yaml
default_provider: openrouter
fallback_providers:
  - litellm
  - ollama
```

**Per-provider** (tried before profile-level fallbacks):

```yaml
providers:
  openrouter:
    base_url: https://openrouter.ai/api/v1
    default_model: anthropic/claude-sonnet-4
    fallback_providers:
      - litellm
  litellm:
    base_url: http://localhost:4000/v1
    default_model: smart
  ollama:
    base_url: http://127.0.0.1:11434/v1
    default_model: qwen2.5-coder:32b
```

CLI:

```bash
holix models fallback list
holix models fallback set litellm,ollama
holix models fallback clear
```

Each fallback uses that provider's `default_model`. Inherited from `global/config.yaml` unless overridden in the profile.

## Models

Provider presets, `agent_models`, and fallbacks — canonical guide: **[MODELS.md](MODELS.md)** (not duplicated here).

## MCP and Hub

- MCP servers and assignments — **[MCP.md](MCP.md)** and `holix mcp` in [CLI.md](CLI.md)
- Hub lockfile: `{profile}/data/hub-lock.json` — [HUB.md](HUB.md)
- `skill_assignments` — per-agent skill allowlists: `holix skills assign`

## Plan generation (Plan & Hybrid modes)

Profile `.env` / `config.yaml` (see also [EXECUTION_MODES.md](EXECUTION_MODES.md#settings)):

| Variable | Default | Effect |
|----------|---------|--------|
| `plan_review_enabled` | `true` | Show plan for approval before execution |
| `plan_review_timeout` | `600` | Seconds to wait for plan approval |
| `plan_generation_timeout` | `600` | Seconds to wait for LLM plan generation |
| `plan_generation_max_tokens` | `12000` | Max tokens for plan JSON (large development reports) |
| `plan_generation_retries` | `2` | Retries on timeout or truncated JSON |
| `max_steps_per_plan_step` | `5` | Tool iterations per plan step |
| `max_steps` | `15` | Overall graph step limit |

## Local project supplements

In a project directory, Holix may merge (without overwriting profile system keys):

- `./.holix/skills/` — extra skills
- `./.holix/plans/` — approved execution plans (`.md` human-readable, `.json` machine-readable); legacy `./.holix/plan/` is still read if present
- `./config.yaml` — supplemental MCP/skills (not full profile replacement)

## Related

- [INSTALLATION.md](INSTALLATION.md)
- [CLI.md](CLI.md)
- [SECURITY.md](SECURITY.md)