# External CLI launch (`holix launch`)

Run third-party coding agents (Claude Code, OpenCode, Grok Build, …) in **tmux** with LLM credentials from your **Holix profile**. Linux and macOS only.

## Requirements

- **tmux** — `brew install tmux` or `apt install tmux`
- **Holix profile** with a configured model — `holix models setup -p <profile>`
- Supported CLI binary installed (or use `holix launch setup` auto-install where available)

```bash
holix launch list          # supported CLIs and bindings
holix launch setup         # interactive install + profile binding
holix launch claude        # open Claude Code in tmux (attach)
holix launch claude status # binding, model, env, active sessions
```

---

## Supported agents

| ID | Name | Model mapping | Auto-install |
|----|------|---------------|--------------|
| `claude` | Claude Code | `ANTHROPIC_*` + LiteLLM gateway options | `npm install -g @anthropic-ai/claude-code` |
| `opencode` | OpenCode | `OPENCODE_CONFIG` → Holix-managed `opencode.json` (`holix/<model>`) | `curl … opencode.ai/install \| bash` |
| `grok-build` | Grok Build | `GROK_HOME` → Holix-managed `config.toml` + `-m <model>` | `curl … x.ai/cli/install.sh \| bash` |
| `gigacode` | GigaCode | `GIGACODE_*` + `OPENAI_*` fallback | manual |
| `aider` | Aider | `OPENAI_*` / `LLM_MODEL` | `uv tool install aider-chat` |

> **Codex CLI and Codex App** (`codex`, `codex-app`) are temporarily disabled in this release.

Default model slot for coding agents: **`coder`** (configure in `holix models setup` or per-binding in `holix launch setup`).

---

## Quick start

```bash
# 1. Configure LLM in Holix profile
holix models setup -p default

# 2. Bind external CLIs for the profile
holix launch setup

# 3. Open an agent (reuses last session if still alive)
holix launch claude
holix launch opencode -t "fix failing tests"
holix launch grok-build --detach -t "refactor auth module"

# 4. Inspect binding and env
holix launch opencode status
```

### Per-agent subcommands

Each registered CLI is a Typer app under `holix launch <id>`:

| Invocation | Action |
|------------|--------|
| `holix launch <id>` | Open CLI in tmux (attach, or reuse existing session) |
| `holix launch <id> status` | Binding, model config, env preview, active sessions |

Shared options on `holix launch <id>`:

| Option | Short | Description |
|--------|-------|-------------|
| `--cwd` | `-C` | Working directory |
| `--task` | `-t` | Initial prompt (passed on argv where supported) |
| `--model-slot` | `-m` | Profile model slot (`main`, `coder`, …) |
| `--detach` | | Start in background without attaching |
| `--new` | `-n` | Always create a new tmux session |
| `--window` | `-w` | New window in existing session |
| `--session` | `-s` | Target tmux session for `--window` |

---

## Setup wizard

```bash
holix launch setup
holix launch setup -y    # non-interactive: enable all installed CLIs
```

The wizard:

1. Lists CLIs and install status
2. Offers **automatic install** when `install_commands` are defined (OpenCode, Grok Build, Claude, Aider)
3. Detects binaries in standard paths (`~/.opencode/bin`, `~/.grok/bin`, …) even before PATH is updated
4. For each enabled CLI asks:
   - **Model slot** — which profile model slot feeds the external CLI (`coder` by default)
   - **Assign to sub-agent** — which Holix sub-agent type may launch this CLI via the `external_cli` tool (`coder`, `researcher`, …)
5. Saves per-profile bindings to `~/.holix/profiles/<profile>/external_clis/bindings.json`

Example binding:

```json
{
  "bindings": [
    {
      "cli_id": "claude",
      "enabled": true,
      "command": "/usr/local/bin/claude",
      "model_slot": "coder",
      "agent_slot": "coder",
      "default_cwd": "/path/to/project"
    }
  ]
}
```

Only the assigned sub-agent type with `enabled: true` can use `external_cli` to launch or message that CLI. Manual `holix launch claude` from the terminal is not restricted.

---

## Session management

| Command | Description |
|---------|-------------|
| `holix launch sessions` | Holix-managed tmux sessions for this profile |
| `holix launch tmux` | All tmux sessions on the machine |
| `holix launch attach <id\|tmux_name>` | Attach to session (`Ctrl+b d` to detach) |
| `holix launch send <id> "prompt"` | Send text + Enter to running CLI |
| `holix launch chat <id>` | Interactive relay (text + arrow keys for menus) |
| `holix launch output <id>` | Capture recent pane output (`-n` lines) |
| `holix launch kill <id>` | Stop tmux session |

Session refs: Holix session id (short hex) or tmux session name (`holix-<profile>-<cli>-<suffix>`).

---

## Model integration by agent

Holix maps the active profile model (from slot `coder` by default) into each CLI’s expected configuration.

### Claude Code (`claude`)

- Env: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` (strips trailing `/v1` for gateway)
- LiteLLM / custom gateways: `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`, `ANTHROPIC_CUSTOM_MODEL_OPTION` for non-Anthropic model ids (e.g. `coder`)

### OpenCode (`opencode`)

OpenCode does **not** read `OPENAI_BASE_URL` alone. Holix writes:

```
~/.holix/profiles/<profile>/opencode/opencode.json
```

and sets `OPENCODE_CONFIG` to that path. The config defines provider `holix` with `@ai-sdk/openai-compatible`, your `base_url`, `api_key`, and default model `holix/<model_id>`. Launch uses `-m holix/<model_id>`.

### Grok Build (`grok-build`)

Holix writes:

```
~/.holix/profiles/<profile>/grok/config.toml
```

with `[model.<name>]` for your LiteLLM/OpenAI-compatible endpoint, sets `GROK_HOME`, `XAI_API_KEY`, `GROK_MODELS_BASE_URL`. Initial task is passed as a **positional prompt** on the command line (not only via tmux `send-keys`). Symlinks `~/.grok/auth.json` when present.

### Aider / GigaCode

Standard env mapping: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` (Aider); `GIGACODE_*` plus OpenAI fallback (GigaCode).

---

## Interactive relay (`holix launch chat`)

Use when the external CLI shows choice menus (permissions, model picker, numbered options):

- Type prompts as usual
- **Arrow keys**, Tab, Escape forwarded to tmux
- Digits `1`–`9` without text → quick option select
- `Ctrl+C` exits relay (tmux session keeps running)

---

## Profile paths

| Path | Content |
|------|---------|
| `~/.holix/profiles/<p>/external_clis/bindings.json` | Per-CLI `enabled`, binary path, `model_slot`, `agent_slot`, default cwd |
| `~/.holix/profiles/<p>/external_clis/sessions.json` | Active Holix launch sessions |
| `~/.holix/profiles/<p>/opencode/opencode.json` | OpenCode provider config (generated on launch) |
| `~/.holix/profiles/<p>/grok/config.toml` | Grok Build model config (generated on launch) |

---

## Agent tool (`external_cli`)

Assigned **sub-agents** can launch or message external CLIs via the `external_cli` tool (`action`: `launch`, `send`, `output`, `list_sessions`). Same profile models and tmux sessions as the CLI.

**Access rules:**

| Caller | Can use `external_cli`? |
|--------|-------------------------|
| Main agent | No — tool is hidden from the main agent |
| Sub-agent without assignment | No |
| Sub-agent matching `agent_slot` with `enabled: true` | Yes — tool is injected into that sub-agent's tool list |

Typical flow:

```
Main agent → delegate_to_subagent(coder, "refactor auth in Claude Code")
Sub-agent coder → external_cli(action=launch, cli_id=claude, task="…")
```

Configure assignment in `holix launch setup` (field **Assign to sub-agent**) or in TUI:

```text
/launch        # modal: assign / unassign sub-agent per CLI
/launch list   # print assignments in the transcript
```

See [LAUNCH_SUBAGENTS.md](LAUNCH_SUBAGENTS.md).

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `tmux is required` | Install tmux |
| `Binary not found` | `holix launch setup` or install manually; wizard checks `~/.opencode/bin`, `~/.grok/bin` |
| OpenCode ignores Holix model | `holix launch opencode status` — expect `OPENCODE_CONFIG` and model `holix/...` |
| Grok task not applied | Use `-t`; task is argv positional: `grok -m coder "your task"` |
| Claude `coder` model error | Gateway base URL must not include `/v1`; Holix normalizes automatically |

---

## See also

- [LAUNCH_SUBAGENTS.md](LAUNCH_SUBAGENTS.md) — Holix sub-agents and `holix launch`
- [CLI.md](CLI.md) — full `holix` reference
- [PROFILES.md](PROFILES.md) — profile layout and model slots
- [CONFIGURATION.md](CONFIGURATION.md) — providers and `agent_models`