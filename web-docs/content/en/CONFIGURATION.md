# Configuration

## Layers

1. **Shell environment** — highest priority (never overwritten by files)
2. **Profile `.env`** — `~/.helix/profiles/<name>/.env` (overrides only)
3. **Global `.env`** — `~/.helix/global/.env` (shared API keys, voice, tool flags)
4. **Legacy global `.env`** — `~/.helix/.env` (fallback when `global/.env` is missing)
5. **Project `.env`** — `./.env` in CWD (dev convenience)
6. **Profile YAML** — `~/.helix/profiles/<name>/config.yaml` (per-profile overrides)
7. **Global YAML** — `~/.helix/global/config.yaml` (shared models, MCP, behavior)
8. **CLI flags** — overrides per command

**Inheritance:** profiles created with `--inherit` (default) load global settings first; anything set in the profile file overrides global. Change global once → all inheriting profiles pick it up on next start (for keys not overridden in the profile).

```bash
helix profile global edit              # shared models, MCP, behavior
helix profile global edit --env        # shared env (Whisper, gateway defaults, …)
helix -p alice profile env --edit      # profile-only overrides
helix profile create bob               # inherits global (default)
helix profile create carol --clean     # standalone profile, manual setup
```

## Data directory (`HELIX_HOME`)

| OS | Default |
|----|---------|
| Linux / macOS | `~/.helix` |
| Windows | `%LOCALAPPDATA%\Helix` |
| Override | `HELIX_HOME` |
| Linux (XDG) | `$XDG_DATA_HOME/helix` |

Shared under `HELIX_HOME`: `global/` (shared settings), logs, MCP server clones. **Per profile** under `profiles/<name>/`: `.env`, `config.yaml`, `telegram.env`, `gateway/`, `data/`.

### Global layout

| Path | Content |
|------|---------|
| `global/config.yaml` | Shared models, providers, MCP, search, agent behavior |
| `global/.env` | Shared API keys, Whisper/voice, gateway defaults, tool flags |

Initialized on first run (seeded from `profiles/default/config.yaml` when present, else built-in defaults). Manage with `helix profile global show|edit|init`.

### Profile layout

| Path | Content |
|------|---------|
| `profiles/<name>/.env` | Overrides only (unset keys inherit from `global/.env`) |
| `profiles/<name>/telegram.env` | Bot token, allowlist, `HELIX_TELEGRAM_USER_PROFILES` |
| `profiles/<name>/telegram-users.json` | Telegram user id → Helix profile bindings |
| `profiles/<name>/gateway/state.json` | Running gateway PID and bind |
| `profiles/<name>/config.yaml` | Overrides only (inherits `global/config.yaml`) |
| `profiles/<name>/data/` | Memory, skills, security, cron |

## Workspace jail (optional)

Restrict file and terminal tools to one directory tree — useful when several people share one machine with separate profiles.

```bash
helix -p data-agent profile jail enable ~/data-agent
helix -p data-agent profile jail status
helix -p data-agent profile jail disable
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
helix -p dev profile whitelist enable
helix -p dev profile whitelist add "ls, cat, python, git"
helix -p dev profile whitelist list
```

Equivalent `.env` variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_TERMINAL_COMMAND_WHITELIST` | `true` | Enforce whitelist for `run_terminal_command` |
| `HELIX_TERMINAL_WHITELIST_EXTRA` | empty | Comma-separated extra commands or prefixes |

Platform defaults are always included. See [SECURITY.md](SECURITY.md).

## Telegram (shared bot, multiple users)

**Recommended** — access requests (`helix telegram setup` enables this by default):

```bash
helix -p shared telegram requests approve USER_ID --create-profile ivan
```

**Manual** bindings when one bot serves several Helix profiles:

```bash
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map import "111:alice,222:bob"
```

| Variable / file | Description |
|-----------------|-------------|
| `HELIX_TELEGRAM_ACCESS_REQUESTS` | `true` — users send `/start`, admin approves via CLI (default after `telegram setup`) |
| `HELIX_TELEGRAM_ADMIN_USER_ID` | Single Telegram admin user id (set via `requests approve --set-admin`; CLI only) |
| `HELIX_TELEGRAM_ADMIN_PROFILE` | Helix profile for the admin (default: `admin`) |
| `telegram-access-requests.json` | Pending/resolved access requests per bot profile |
| `HELIX_TELEGRAM_ALLOWED_USERS` | Manual allowlist (optional when access requests are on) |
| `HELIX_TELEGRAM_USER_PROFILES` | `USER_ID:profile` comma-separated in `telegram.env` |
| `telegram-users.json` | User bindings; updated by `map` or `requests approve` |

Details: [TELEGRAM.md](TELEGRAM.md), [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

## Key environment variables

See [.env.example](../../.env.example).

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_LOG_LEVEL` | `INFO` | Root log level (`LOG_LEVEL` alias) |
| `HELIX_LOG_DEBUG` | `false` | Enable debug log file (`LOG_DEBUG` alias) |
| `HELIX_LOG_MAX_BYTES` | `10485760` | Rotate when file exceeds size (bytes) |
| `HELIX_LOG_BACKUP_COUNT` | `10` | Rotating backup files to keep |
| `HELIX_LOG_ROTATION_DAYS` | `14` | Purge backups older than N days |

CLI: `helix logs debug on|off` persists to `logs/logging.json`.  
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
helix models presets          # OpenAI, OpenRouter, DeepSeek, Kimi, Grok, Groq, …
helix models add openrouter   # quick add from catalog
helix models add ollama --host 192.168.1.10:11434
helix models add litellm --host http://proxy.local:4000
helix models add vllm --host gpu-node:8000
helix models setup            # interactive wizard (prompts for host on local presets)
helix models list
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

CLI: `--host` and optional `--port` on `helix models add`. Wizard and `add` read env vars when set (see [.env.example](../../.env.example)).

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
      x_title: Helix
```

Legacy top-level fields (`model`, `base_url`) still work; prefer `providers` + `default_provider`.

### Provider fallback (when LLM is unavailable)

If the primary provider fails (connection error, timeout, rate limit, model not found), Helix tries **fallback providers** in order and switches the active client for the rest of the session step.

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
helix models fallback list
helix models fallback set litellm,ollama
helix models fallback clear
```

Each fallback uses that provider's `default_model`. Inherited from `global/config.yaml` unless overridden in the profile.

## MCP and Hub

- `mcp_servers`, `mcp_assignments` — see `helix mcp` in [CLI.md](CLI.md)
- Hub lockfile: `{profile}/data/hub-lock.json` — [HUB.md](HUB.md)
- `skill_assignments` — per-agent skill allowlists: `helix skills assign`

## Local project supplements

In a project directory, Helix may merge (without overwriting profile system keys):

- `./.helix/skills/` — extra skills
- `./.helix/plan/` — plan files
- `./config.yaml` — supplemental MCP/skills (not full profile replacement)

## Related

- [INSTALLATION.md](INSTALLATION.md)
- [CLI.md](CLI.md)
- [SECURITY.md](SECURITY.md)