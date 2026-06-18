# Models and providers

Holix routes LLM calls through **providers** in profile `config.yaml`. Use **`holix models`** to configure presets, per-agent routing, and fallbacks.

---

## Quick setup

```bash
holix models setup
holix models list
holix models agents
holix models fallback list
```

Wizard probes connectivity and writes `default_provider`, `providers`, and `agent_models`.

---

## Providers

Built-in presets (wizard adds API keys to profile `.env`):

| Preset | Typical use |
|--------|-------------|
| `openrouter` | Cloud models via OpenRouter |
| `openai` | OpenAI API |
| `groq` | Groq |
| `ollama` | Local Ollama (`OLLAMA_HOST`, default port 11434) |
| `litellm` | LiteLLM proxy (`LITELLM_API_BASE`, port 4000) |
| `vllm` | vLLM OpenAI server (`VLLM_HOST`, port 8000) |

Example fragment:

```yaml
default_provider: litellm
providers:
  litellm:
    base_url: http://127.0.0.1:4000/v1
    api_key: ${LITELLM_API_KEY}
    default_model: smart
  ollama:
    base_url: http://127.0.0.1:11434/v1
    default_model: qwen2.5-coder:32b
```

Host env vars accept hostname, `host:port`, or full URL — see [CONFIGURATION.md](CONFIGURATION.md).

Legacy top-level `model` / `base_url` still work; prefer `providers` + `default_provider`.

---

## Per-agent routing (`agent_models`)

Route different agents (main chat, sub-agent slots, plan steps) to different models:

```yaml
agent_models:
  main:
    provider: litellm
    model: smart
  coder:
    provider: litellm
    model: heavy
  code-reviewer:
    provider: ollama
    model: qwen2.5-coder:32b
```

CLI: `holix models agents`

In chat: `/models` (TUI) or `/model <name>` (`chat-command`).

Sub-agents use the **parent model** by default unless the sub-agent type sets a model slot — [SUBAGENTS.md](SUBAGENTS.md).

---

## Fallback providers

When the primary provider fails (timeout, rate limit, connection error), Holix tries fallbacks in order.

**Profile-level:**

```yaml
fallback_providers:
  - litellm
  - ollama
```

**Per-provider:**

```yaml
providers:
  openrouter:
    fallback_providers:
      - litellm
```

```bash
holix models fallback set litellm,ollama
holix models fallback clear
```

Inherited from `~/.holix/global/config.yaml` unless overridden in the profile.

---

## Global vs profile

| Layer | Path |
|-------|------|
| Global defaults | `~/.holix/global/config.yaml` |
| Profile override | `~/.holix/profiles/<name>/config.yaml` |
| Secrets | profile `.env` (`${OPENROUTER_API_KEY}`, …) |

```bash
holix profile global edit
holix -p work profile env --edit
holix config show
```

---

## Gateway and API

- `GET /v1/models` — models from active profile ([GATEWAY.md](GATEWAY.md))
- Management: `/api/holix/profiles/{id}/models` — [GATEWAY_API.md](GATEWAY_API.md)

---

## Troubleshooting

```bash
holix doctor
holix doctor --fix
holix models setup
```

| Symptom | Check |
|---------|--------|
| Wrong model in TUI | `/status`, `holix config show`, `agent_models` |
| All providers fail | `base_url`, API keys in `.env`, network to Ollama/LiteLLM |
| Sub-agent uses parent model | Expected unless type has model slot |

---

## See also

- [CONFIGURATION.md](CONFIGURATION.md) — env variables for hosts
- [CLI.md](CLI.md#holix-models) — command reference
- [EXECUTION_MODES.md](EXECUTION_MODES.md) — plan generation token limits