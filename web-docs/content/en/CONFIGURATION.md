# Configuration

## Layers

1. **Shell environment** — highest priority (never overwritten by files)
2. **Profile `.env`** — `~/.helix/profiles/<name>/.env` (API keys, gateway bind, feature flags)
3. **Legacy global `.env`** — `~/.helix/.env` (fallback for older installs)
4. **Project `.env`** — `./.env` in CWD (dev convenience)
5. **Profile YAML** — `~/.helix/profiles/<name>/config.yaml` (models, MCP, skills)
6. **CLI flags** — overrides per command

Each profile is isolated: own env file, Telegram secrets, gateway process state, memory, and skills.

```bash
helix -p alice profile env --edit    # edit profiles/alice/.env
cp .env.example ~/.helix/profiles/default/.env   # first-time seed
```

## Data directory (`HELIX_HOME`)

| OS | Default |
|----|---------|
| Linux / macOS | `~/.helix` |
| Windows | `%LOCALAPPDATA%\Helix` |
| Override | `HELIX_HOME` |
| Linux (XDG) | `$XDG_DATA_HOME/helix` |

Shared under `HELIX_HOME`: logs, MCP server clones. **Per profile** under `profiles/<name>/`: `.env`, `config.yaml`, `telegram.env`, `gateway/`, `data/`.

### Profile layout

| Path | Content |
|------|---------|
| `profiles/<name>/.env` | API keys, `HELIX_GATEWAY_PORT`, tool flags |
| `profiles/<name>/telegram.env` | Bot token and allowlist |
| `profiles/<name>/gateway/state.json` | Running gateway PID and bind |
| `profiles/<name>/config.yaml` | Models, MCP, hub, workspace jail |
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