# Helix — Complete User Guide

Step-by-step instructions: install from `.whl`, initial setup, LiteLLM connection, MCP, skills, Telegram, and execution modes.

> All commands and paths are taken from the Helix repository (`cli/`, `docs/`, `config.py`, `pyproject.toml`).  
> The package is named **`HelixAgentAi`**; the terminal command is **`helix`**.

---

## Table of Contents

1. [What Helix Can Do](#1-what-helix-can-do)
2. [Requirements](#2-requirements)
3. [Step 1 — Install Python](#3-step-1--install-python)
4. [Step 2 — Install UV (recommended)](#4-step-2--install-uv-recommended)
5. [Step 3 — Install from PyPI](#5-step-3--install-from-pypi)
6. [Step 4 — First Run and Profile](#6-step-4--first-run-and-profile)
7. [Step 5 — Configure Models via LiteLLM](#7-step-5--configure-models-via-litellm)
8. [Step 6 — Web Search (optional)](#8-step-6--web-search-optional)
9. [Step 7 — Telegram Bot](#9-step-7--telegram-bot)
10. [Step 8 — Execution Modes](#10-step-8--execution-modes)
11. [Step 9 — How to Write Prompts](#11-step-9--how-to-write-prompts)
12. [Step 10 — MCP Step by Step](#12-step-10--mcp-step-by-step)
13. [Step 11 — Skills and Hub Plugins](#13-step-11--skills-and-hub-plugins)
14. [CLI Reference](#14-cli-reference)
15. [Slash Commands `/` in Chat](#15-slash-commands--in-chat)
16. [Helix Features](#16-helix-features)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. What Helix Can Do

Helix is an AI agent with:

- **tool calling** — files, terminal, web, code, optional browser (Playwright);
- **memory** — SQLite + semantic search (ChromaDB);
- **skills** — markdown instructions, Hub catalogs (ClawHub, Hermes, Claude plugins);
- **MCP** — connect external Model Context Protocol servers;
- **multiple interfaces** — TUI (`helix tui`), chat (`helix chat-command`), single request (`helix run`), API (`helix gateway`), Telegram;
- **security** — confirmation for dangerous actions, command whitelist, API keys;
- **subagents** — background tasks in separate processes;
- **planning** — modes with plan review and step approval.

Data is stored in **`~/.helix/`** (Linux/macOS) or **`%LOCALAPPDATA%\Helix\`** (Windows).

---

## 2. Requirements

| Component | Version / note |
|-----------|--------------|
| **Python** | **3.12+** (`requires-python` in `pyproject.toml`) |
| **uv** | recommended for installing dependencies |
| **LLM** | OpenAI-compatible API (this guide uses **LiteLLM**) |
| **Node.js / npx** | required for many MCP servers (`helix doctor` will check) |
| **Docker** | optional (e.g., MCP GitHub) |

---

## 3. Step 1 — Install Python

1. Open [https://www.python.org/downloads/](https://www.python.org/downloads/).
2. Download **Python 3.12** or newer.
3. Install. On Windows, check **“Add Python to PATH”**.
4. Verify in the terminal:

```bash
python3 --version
# or on Windows:
python --version
```

You should see **3.12.x** or higher.

---

## 4. Step 2 — Install UV (recommended)

UV is a fast Python package manager. Helix documentation recommends it for development and installation.

**macOS / Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Verify:**

```bash
uv --version
```

Alternative without UV: plain `pip` (see step 5).

---

## 5. Step 3 — Install from PyPI

Package **[HelixAgentAi](https://pypi.org/project/HelixAgentAi/)** on PyPI; terminal command **`helix`**.

> Do not use `pip install helix` — on PyPI that is a **different** project.

### 5.1. Global install (recommended)

```bash
pipx install HelixAgentAi
helix version
```

With optional extras (Telegram, browser, web TUI, voice):

```bash
pipx install "HelixAgentAi[all]"
# or: pipx install "HelixAgentAi[telegram,browser,tui-web]"
```

Alternative: `uv tool install HelixAgentAi`

### 5.2. Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install HelixAgentAi
pip install "HelixAgentAi[telegram]"
helix version
```

### 5.3. User install (`~/.local/bin`)

```bash
pip install --user HelixAgentAi
export PATH="$HOME/.local/bin:$PATH"
helix version
```

### 5.4. Windows

PowerShell install, `%LOCALAPPDATA%\Helix\` paths, and troubleshooting: [INSTALLATION.md — Windows](INSTALLATION.md#windows).

```powershell
pipx install HelixAgentAi
helix version
# or from git clone:
.\scripts\install.ps1
```

### 5.5. Alternative — install from a `.whl` file

For offline machines or CI artifacts, build or download a wheel:

```bash
# build from source:
uv build && ls dist/helixagentai-*.whl

pipx install /path/to/helixagentai-0.1.3-py3-none-any.whl
# or: uv tool install /path/to/helixagentai-*.whl
```

### 5.6. Post-install verification

```bash
helix --help
helix doctor
```

---

## 6. Step 4 — First Run and Profile

### 6.1. Create the environment file

On first profile creation, Helix seeds **`~/.helix/profiles/<name>/.env`** from `.env.example` (or copies legacy `~/.helix/.env` if present).

```bash
helix profile env --edit
# or manually:
cp .env.example ~/.helix/profiles/default/.env
```

API keys, gateway port, and feature flags belong in the **profile** `.env`, not the global `~/.helix/.env` (legacy fallback only).

### 6.2. Profile

Each profile is an isolated environment:

```
~/.helix/profiles/<name>/.env           # secrets and gateway bind
~/.helix/profiles/<name>/telegram.env  # Telegram bot (optional)
~/.helix/profiles/<name>/gateway/        # gateway state and log
~/.helix/profiles/<name>/config.yaml
~/.helix/profiles/<name>/data/
```

The **`default`** profile is used by default. On first run, Helix creates the required directories.

**Workspace jail** (optional): restrict file/terminal tools to one folder — `helix profile jail enable /path/to/dir`. See [CONFIGURATION.md](CONFIGURATION.md).

**Terminal whitelist** (optional): `helix profile whitelist enable`, `whitelist add "docker, make"`, `whitelist list` — see [PROFILES.md](PROFILES.md).

View settings:

```bash
helix status
helix config show
```

Switch profile:

```bash
helix -p work tui
```

In chat: `/profile work` or `/profile` (list).

### 6.3. Diagnostics

```bash
helix doctor
helix doctor --fix
```

Doctor checks: directories, YAML, LLM, gateway, Telegram, MCP env, platform (node/npx/git).

---

## 7. Step 5 — Configure Models via LiteLLM

When running LiteLLM locally, the default endpoint is:

**`http://localhost:4000`**

Helix talks to LiteLLM through the **OpenAI-compatible API** (`/v1/chat/completions`, `/v1/models`).

### 7.1. What to get from the LiteLLM administrator

1. **Virtual API key** (client key) — stored as `LITELLM_API_KEY`.
2. A list of **model names** (`model_name` in the LiteLLM config) that you are allowed to use.  
   The Helix catalog for the `litellm` preset lists examples: `smart`, `fast`, `heavy` — **actual names on your server may differ**; Helix will show the list on successful connection.

### 7.2. Save the key in the profile `.env`

Open `~/.helix/profiles/default/.env` (`helix profile env --edit`) and add:

```bash
# LiteLLM proxy
LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=sk-your-virtual-key-from-litellm
```

> Helix substitutes `${LITELLM_API_KEY}` and the host from `LITELLM_API_BASE` into the profile `config.yaml`.

Optional API availability check (from the user's machine):

```bash
curl -s http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_API_KEY" | head
```

The response should be JSON with a list of models.

### 7.3. Add the LiteLLM provider to the profile (interactive)

```bash
helix models add litellm --host http://localhost:4000
```

What happens:

1. Helix prompts for the API key (if `LITELLM_API_KEY` is already in `.env` — it uses that).
2. Connects to `http://localhost:4000/v1`.
3. Loads the model list from `/v1/models`.
4. Asks you to choose the **default model** for this provider.
5. Saves settings to `~/.helix/profiles/default/config.yaml`.

### 7.4. Full setup wizard (recommended)

```bash
helix models setup
```

In the menu:

| Option | Action |
|--------|--------|
| **1** | Add provider (choose **litellm** preset, # from the table) |
| **2** | List providers |
| **3** | Test connection |
| **5** | **Assign models to agents** (`main`, subagents) |
| **7** | Save and exit |

### 7.5. Assigning models to agents

In `helix models setup` → option **5** (Configure agent models):

- **`main`** — primary agent in chat;
- you can assign different models to subagents (`researcher`, `coder`, …).

View assignments:

```bash
helix models agents
```

### 7.6. Example `config.yaml` fragment after setup

```yaml
default_provider: litellm
providers:
  litellm:
    base_url: http://localhost:4000/v1
    api_key: ${LITELLM_API_KEY}
    default_model: <model-name-from-litellm-list>
    metadata:
      auth_type: bearer
      preset_id: litellm
agent_models:
  main:
    provider: litellm
    model: <model-name-from-litellm-list>
    temperature: 0.7
```

### 7.7. Apply changes

If gateway or Telegram is running:

```bash
helix gateway reload
```

In TUI, switch models on the fly: `/models` or `/model`.

---

## 8. Step 6 — Web Search (optional)

Helix supports providers: **DuckDuckGo** (default), **SearXNG**, **Firecrawl**.

```bash
helix search configure   # interactive provider selection and order
helix search list
helix search test "test query"
```

In chat: `/search`, `/search configure`, `/search test query`.

After configuration: `helix gateway reload`.

Secrets in `.env`: `FIRECRAWL_API_KEY`, `SEARXNG_BASE_URL` (see `.env.example`).

---

## 9. Step 7 — Telegram Bot

### 9.1. Install the Telegram dependency

```bash
uv sync --extra telegram
# or when installing the wheel:
pip install "HelixAgentAi[telegram]"
```

### 9.2. Create a bot in Telegram

1. Open Telegram and find **[@BotFather](https://t.me/BotFather)**.
2. Send the **`/newbot`** command.
3. Enter the bot **display name**.
4. Enter the bot **username** (must end with `bot`, e.g. `my_company_helix_bot`).
5. BotFather will send a **token** like `123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — save it.

### 9.3. Find your Telegram user id

Required to restrict access (who can message the bot):

- message [@userinfobot](https://t.me/userinfobot), or
- the `helix telegram setup` wizard can detect the id automatically.

### 9.4. Interactive Helix setup

```bash
helix telegram setup
```

The wizard:

1. Validates the token via the Telegram API (`getMe`).
2. Asks for the user **allowlist** (`HELIX_TELEGRAM_ALLOWED_USERS`).
3. Saves settings to **`~/.helix/profiles/<name>/telegram.env`**.
4. When multiple Helix profiles exist, offers **user id → profile** bindings (one bot, many users).

### 9.4.1. User id → profile mapping (shared bot)

```bash
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map bind bob --user-id 987654321
helix -p shared telegram map list
```

Details: [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

### 9.5. Start the bot

**Standalone:**

```bash
helix telegram run
# or simply:
helix telegram
```

**Together with the API gateway** (recommended for always-on use):

```bash
helix gateway start
```

The gateway supervisor also starts Telegram if it is configured.

### 9.6. Update the Telegram command menu

```bash
helix telegram sync-menu
```

After changing skills, MCP, or slash commands.

### 9.7. Voice messages (optional)

If chat already goes through LiteLLM, configure the transcription model **in the LiteLLM config** and in the profile `.env`:

```bash
HELIX_WHISPER_BASE_URL=http://localhost:4000/v1
HELIX_WHISPER_API_KEY=sk-...          # LiteLLM virtual key
HELIX_WHISPER_MODEL=whisper           # model_name from LiteLLM (not whisper-1)
HELIX_TELEGRAM_VOICE_LANGUAGE=en
```

More details: [TELEGRAM.md](TELEGRAM.md).

### 9.8. Production

When `HELIX_ENV=production`, `HELIX_TELEGRAM_ALLOWED_USERS` is required.

---

## 10. Step 8 — Execution Modes

Helix supports four execution modes in TUI and Telegram:

| Mode | Name | When to use |
|------|------|-------------|
| **ReAct** | `react` | Quick questions, tools, exploration (default) |
| **Plan** | `plan_and_execute` | Multi-step tasks with clear subgoals |
| **Hybrid** | `hybrid` | Large tasks: plan first, flexible work per step |
| **Auto** | `auto` | Helix picks the best mode via a classifier |

Switch with **`/mode`**, **`/mode <name>`**, or **Shift+Tab** (legacy TUI). Plan modes use `/plan-confirm`, `/plan-auto`, `/plan-refine`, `/plan-reject`. Risky tools use `/yes`, `/1`–`/4`.

**Full guide with diagrams, behaviour, settings, and prompt examples:** [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## 11. Step 9 — How to Write Prompts

1. Specify **file paths** and the **expected outcome**.
2. For code — language, framework, constraints.
3. Commands starting with `/` are **slash commands**; they do **not** go to the LLM (`/help`, `/mode`, …).
4. Match task size to mode — see prompt examples per mode in [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## 12. Step 10 — MCP Step by Step

MCP (Model Context Protocol) adds external tools (GitHub, filesystem, documentation, etc.).

### 12.1. Browse popular servers

```bash
helix mcp list-popular
```

Examples from the catalog: `filesystem`, `github`, `context7`, `compass`, `postgres`, …

### 12.2. Install MCP (easy way)

```bash
helix mcp install
```

Interactive: pick from the list → enter parameters (paths, API keys) → test → save to profile.

Or by name:

```bash
helix mcp install context7
helix mcp install filesystem
```

From git:

```bash
helix mcp install https://github.com/upstash/context7
```

### 12.3. Assign MCP to agents

```bash
helix mcp assign
```

For example: `main` sees `filesystem` and `context7`, subagent `researcher` — only `context7`.

Verify:

```bash
helix mcp list
helix mcp test <server-name>
helix mcp tools
```

### 12.4. Full wizard

```bash
helix mcp setup
```

Add servers + assign to roles.

### 12.5. In chat (TUI / Telegram)

```
/mcp
/mcp list
/mcp install
/mcp assign
/mcp test filesystem
/mcp tools
/mcp remove <name>
```

### 12.6. Apply

```bash
helix gateway reload
```

MCP tools in the agent are named **`mcp_<server>_<tool>`**.

### 12.7. Environment variables for MCP

Secrets in MCP config: `${GITHUB_TOKEN}`, `${CONTEXT7_API_KEY}`, etc.  
Values go in `~/.helix/.env`.  
`helix doctor` warns about unresolved `${VAR}`.

---

## 13. Step 11 — Skills and Hub Plugins

### 13.1. What are skills

A **skill** is a `SKILL.md` file with instructions for the agent.  
Stored in: `~/.helix/profiles/<profile>/data/skills/`

### 13.2. Install from Hub (CLI)

```bash
# search
helix hub search "docker" -s clawhub
helix hub search "git" -s clawhub

# interactive browse
helix hub browse

# install
helix hub install <spec>
helix hub install <spec> --agents main,coder
```

Spec formats (from Hub documentation):

| Prefix | Example |
|--------|---------|
| ClawHub | `my-skill` or `clawhub:slug@1.0` |
| Claude plugin | `claude:github@claude-official` |
| Hermes | `hermes:api-builder` |
| skills.sh | `skills-sh/owner/repo/path` |
| Git | `git:https://github.com/...` |

Claude plugins may add MCP (`--with-mcp` by default).

### 13.3. In TUI

```
/hub                  — pick catalog
/hub browse           — search and install
/hub installed        — what is installed
/skills               — hint for listing skills
```

### 13.4. Assign skills to agents

By default **`main`** sees all skills in the profile.  
Restrict via `skill_assignments` in `config.yaml`:

```bash
helix skills list --agent main
helix skills assign docker-manager --agents main,coder
helix skills unassign docker-manager --agent coder
helix skills assign-wizard    # interactive
```

### 13.5. Hub updates

```bash
helix hub list
helix hub check-updates
helix hub update
helix hub autoupdate --enable
helix hub slash-sync          # refresh skill-slash.json
```

### 13.6. Apply

```bash
helix gateway reload
```

---

## 14. CLI Reference

Global options: **`--profile` / `-p`**, **`--verbose` / `-v`**.

### Main commands

| Command | Purpose |
|---------|---------|
| `helix tui` | Full-screen interface (recommended) |
| `helix chat-command` | Terminal chat |
| `helix run "query"` | Single request without entering chat |
| `helix status` | Profile status |
| `helix version` | Version |
| `helix clear` | Clear profile data |
| `helix doctor` | Diagnostics |
| `helix install` | Install helix to PATH (from source) |
| `helix update` | Update |

### `helix models`

| Subcommand | Description |
|------------|-------------|
| `setup` | Interactive wizard |
| `add <preset>` | Add provider (`litellm`, `ollama`, …) |
| `presets` | List presets |
| `list` | Providers in profile |
| `agents` | Model assignments per agent |

### `helix config`

| Subcommand | Description |
|------------|-------------|
| `show` | Show YAML |
| `edit` | Editor |
| `set key value` | Change a field |

### `helix mcp`

`list`, `add`, `remove`, `test`, `assign`, `setup`, `list-popular`, `install`

### `helix hub`

`search`, `browse`, `install`, `list`, `remove`, `check-updates`, `update`, `autoupdate`, `slash-sync`

### `helix skills`

`list`, `search`, `show`, `assign`, `unassign`, `agents`, `assign-wizard`

### `helix memory`

`search "<query>"`

### `helix search`

`configure`, `list`, `test`

### `helix gateway`

`start`, `stop`, `status`, `reload`  
Endpoints: `/health`, `/v1/chat/completions`, … — see [GATEWAY.md](GATEWAY.md).

### `helix cron`

Requires a running gateway.  
`add`, `list`, `enable`, `disable`, `remove`

### `helix logs`

`helix logs`, `helix logs -f`, `helix logs -s agent`, `helix logs list`, `helix logs rotate`, `helix logs debug on`

### `helix telegram`

`setup`, `run`, `status`, `sync-menu`, `map set|list|remove|bind|import` — see [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md)

---

## 15. Slash Commands `/` in Chat

Work in **TUI**, **Telegram**, and partially in **`helix chat-command`**.

Full list: [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

Summary:

| Group | Examples |
|-------|----------|
| Help | `/help`, `/status`, `/clear` |
| Models and mode | `/models`, `/mode`, `/stream`, `/stop` |
| Sessions | `/new`, `/sessions`, `/switch N`, `/profile` |
| Memory | `/memory query`, `/memory-clear` |
| Plan | `/plan-confirm`, `/plan-auto`, `/plan-refine`, `/plan-reject` |
| Confirmations | `/yes`, `/no`, `/1`…`/4` |
| MCP | `/mcp`, `/mcp install`, `/mcp assign` |
| Hub | `/hub`, `/hub browse`, `/hub installed` |
| Subagents | `/subagents`, `/subagent-spawn`, `/subagent-result` |
| Search | `/search`, `/search configure`, `/search test` |
| Cron | `/cron`, `/cron add …` |

On macOS with a non-US keyboard layout, `/` may be **Shift+7**.

---

## 16. Helix Features

1. **Profiles** — multiple isolated configurations (`helix -p name`).
2. **Memory** — conversations + long-term memory + semantic search (`/memory`).
3. **Confirmations** — dangerous tool calls require explicit approval.
4. **Plan review** — multi-step tasks are not run silently without your OK (when enabled).
5. **Subagents** — background worker processes; main chat is not blocked (`/subagent-spawn`).
6. **MCP and Hub** — extend without editing agent code.
7. **Multi-interface** — one profile for TUI, Telegram, and API gateway.
8. **Logs** — structured logs for agent/gateway/cron/subagent (`helix logs`).
9. **Doctor** — self-diagnostics for the environment.
10. **OpenAI-compatible API** — gateway for integration with other clients.
11. **Voice in Telegram** — Whisper via LiteLLM, OpenAI, or locally (`faster-whisper`).
12. **Context compression** — `/compress` when the model window overflows.

---

## 17. Troubleshooting

```bash
helix doctor
helix doctor --fix
helix logs -l error -n 50
```

| Problem | What to check |
|---------|---------------|
| `helix: command not found` | PATH, venv, `pipx` / `uv tool` |
| No response from model | `LITELLM_API_KEY`, URL, `helix models list`, curl `/v1/models` |
| MCP not showing up | `helix mcp test`, `helix gateway reload`, `helix doctor` |
| Telegram silent | `helix telegram status`, token, allowlist, `helix gateway status` |
| Stale slash commands | `helix telegram sync-menu`, `helix gateway reload` |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).

---

## Quick checklist: from zero to chat

1. Python 3.12+  
2. `uv` or `pip`  
3. `uv pip install helixagentai-….whl` (or `pipx install …`)  
4. `~/.helix/.env` with `LITELLM_API_BASE` and `LITELLM_API_KEY`  
5. `helix models add litellm --host http://localhost:4000`  
6. `helix models setup` → assign a model for `main`  
7. `helix doctor`  
8. `helix tui` or `helix telegram setup` + `helix gateway start`  
9. As needed: `helix mcp install`, `helix hub browse`, `helix search configure`  

---

## See also

- [INSTALLATION.md](INSTALLATION.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [CLI.md](CLI.md)
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md)
- [TELEGRAM.md](TELEGRAM.md)
- [HUB.md](HUB.md)
- [GATEWAY.md](GATEWAY.md)