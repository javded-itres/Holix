# Holix — Complete User Guide

Step-by-step instructions: install from `.whl`, initial setup, LiteLLM connection, MCP, skills, Telegram, and execution modes.

> All commands and paths are taken from the Holix repository (`cli/`, `docs/`, `config.py`, `pyproject.toml`).  
> The package is named **`Holix`**; the terminal command is **`holix`**.

---

## Table of Contents

1. [What Holix Can Do](#1-what-holix-can-do)
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
16. [Holix Features](#16-holix-features)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. What Holix Can Do

Holix is an AI agent with:

- **tool calling** — files, terminal, web, code, optional browser (Playwright);
- **memory** — SQLite + semantic search (ChromaDB);
- **skills** — markdown instructions, Hub catalogs (ClawHub, Hermes, Claude plugins);
- **MCP** — connect external Model Context Protocol servers;
- **multiple interfaces** — TUI (`holix tui`), chat (`holix chat-command`), single request (`holix run`), API (`holix gateway`), Telegram;
- **security** — confirmation for dangerous actions, command whitelist, API keys;
- **subagents** — background tasks in separate processes;
- **planning** — modes with plan review and step approval.

Data is stored in **`~/.holix/`** (Linux/macOS) or **`%LOCALAPPDATA%\Holix\`** (Windows).

---

## 2. Requirements

| Component | Version / note |
|-----------|--------------|
| **Python** | **3.12+** (`requires-python` in `pyproject.toml`) |
| **uv** | recommended for installing dependencies |
| **LLM** | OpenAI-compatible API (this guide uses **LiteLLM**) |
| **Node.js / npx** | required for many MCP servers (`holix doctor` will check) |
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

UV is a fast Python package manager. Holix documentation recommends it for development and installation.

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

Package **[Holix](https://pypi.org/project/Holix/)** on PyPI; terminal command **`holix`**.

> Do not use `pip install helix` — on PyPI that is a **different** project.

### 5.1. Global install (recommended)

```bash
pipx install Holix
holix version
```

With optional extras (Telegram, browser, web TUI, voice):

```bash
pipx install "Holix[all]"
# or: pipx install "Holix[telegram,browser,tui-web]"
```

Alternative: `uv tool install Holix`

### 5.2. Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install Holix
pip install "Holix[telegram]"
holix version
```

### 5.3. User install (`~/.local/bin`)

```bash
pip install --user Holix
export PATH="$HOME/.local/bin:$PATH"
holix version
```

### 5.4. Windows

PowerShell install, `%LOCALAPPDATA%\Holix\` paths, and troubleshooting: [INSTALLATION.md — Windows](INSTALLATION.md#windows).

```powershell
pipx install Holix
holix version
# or from git clone:
.\scripts\install.ps1
```

### 5.5. Alternative — install from a `.whl` file

For offline machines or CI artifacts, build or download a wheel:

```bash
# build from source:
uv build && ls dist/holix-*.whl

pipx install /path/to/holix-0.1.3-py3-none-any.whl
# or: uv tool install /path/to/holix-*.whl
```

### 5.6. Post-install verification

```bash
holix --help
holix doctor
```

---

## 6. Step 4 — First Run and Profile

### 6.1. Create the environment file

On first profile creation, Holix seeds **`~/.holix/profiles/<name>/.env`** from `.env.example` (or copies legacy `~/.holix/.env` if present).

```bash
holix profile env --edit
# or manually:
cp .env.example ~/.holix/profiles/default/.env
```

API keys, gateway port, and feature flags belong in the **profile** `.env`, not the global `~/.holix/.env` (legacy fallback only).

### 6.2. Profile

Each profile is an isolated environment:

```
~/.holix/profiles/<name>/.env           # secrets and gateway bind
~/.holix/profiles/<name>/telegram.env  # Telegram bot (optional)
~/.holix/profiles/<name>/gateway/        # gateway state and log
~/.holix/profiles/<name>/config.yaml
~/.holix/profiles/<name>/SOUL.md        # agent personality (every session)
~/.holix/profiles/<name>/USER.md        # facts about you
~/.holix/profiles/<name>/INIT.md        # first-run onboarding (temporary)
~/.holix/profiles/<name>/data/
```

The **`default`** profile is used by default. On first run, Holix creates the required directories.

**First chat:** if `INIT.md` is present, the agent introduces itself, learns your name and preferences, and saves them to `USER.md` / `SOUL.md` via built-in tools. Say “save your personality” or “remember my name is …” when ready. Details: [PROFILES.md](PROFILES.md#agent-identity-soul-init-user).

**Workspace jail** (optional): restrict file/terminal tools to one folder — `holix profile jail enable /path/to/dir`. See [CONFIGURATION.md](CONFIGURATION.md).

**Terminal whitelist** (optional): `holix profile whitelist enable`, `whitelist add "docker, make"`, `whitelist list` — see [PROFILES.md](PROFILES.md).

View settings:

```bash
holix status
holix config show
```

Switch profile:

```bash
holix -p work tui
```

In chat: `/profile work` or `/profile` (list).

### 6.3. Diagnostics

```bash
holix doctor
holix doctor --fix
```

Doctor checks: directories, YAML, LLM, gateway, Telegram, MCP env, platform (node/npx/git).

---

## 7. Step 5 — Configure Models via LiteLLM

When running LiteLLM locally, the default endpoint is:

**`http://localhost:4000`**

Holix talks to LiteLLM through the **OpenAI-compatible API** (`/v1/chat/completions`, `/v1/models`).

### 7.1. What to get from the LiteLLM administrator

1. **Virtual API key** (client key) — stored as `LITELLM_API_KEY`.
2. A list of **model names** (`model_name` in the LiteLLM config) that you are allowed to use.  
   The Holix catalog for the `litellm` preset lists examples: `smart`, `fast`, `heavy` — **actual names on your server may differ**; Holix will show the list on successful connection.

### 7.2. Save the key in the profile `.env`

Open `~/.holix/profiles/default/.env` (`holix profile env --edit`) and add:

```bash
# LiteLLM proxy
LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=sk-your-virtual-key-from-litellm
```

> Holix substitutes `${LITELLM_API_KEY}` and the host from `LITELLM_API_BASE` into the profile `config.yaml`.

Optional API availability check (from the user's machine):

```bash
curl -s http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_API_KEY" | head
```

The response should be JSON with a list of models.

### 7.3. Add the LiteLLM provider to the profile (interactive)

```bash
holix models add litellm --host http://localhost:4000
```

What happens:

1. Holix prompts for the API key (if `LITELLM_API_KEY` is already in `.env` — it uses that).
2. Connects to `http://localhost:4000/v1`.
3. Loads the model list from `/v1/models`.
4. Asks you to choose the **default model** for this provider.
5. Saves settings to `~/.holix/profiles/default/config.yaml`.

### 7.4. Full setup wizard (recommended)

```bash
holix models setup
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

In `holix models setup` → option **5** (Configure agent models):

- **`main`** — primary agent in chat;
- you can assign different models to subagents (`researcher`, `coder`, …).

View assignments:

```bash
holix models agents
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
holix gateway reload
```

In TUI, switch models on the fly: `/models` or `/model`.

---

## 8. Step 6 — Web Search (optional)

Holix supports providers: **DuckDuckGo** (default), **SearXNG**, **Firecrawl**.

```bash
holix search configure   # interactive provider selection and order
holix search list
holix search test "test query"
```

In chat: `/search`, `/search configure`, `/search test query`.

After configuration: `holix gateway reload`.

Secrets in `.env`: `FIRECRAWL_API_KEY`, `SEARXNG_BASE_URL` (see `.env.example`).

---

## 9. Step 7 — Telegram Bot

### 9.1. Install the Telegram dependency

```bash
uv sync --extra telegram
# or when installing the wheel:
pip install "Holix[telegram]"
```

### 9.2. Create a bot in Telegram

1. Open Telegram and find **[@BotFather](https://t.me/BotFather)**.
2. Send the **`/newbot`** command.
3. Enter the bot **display name**.
4. Enter the bot **username** (must end with `bot`, e.g. `my_company_holix_bot`).
5. BotFather will send a **token** like `123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — save it.

### 9.3. Connect the bot (admin)

```bash
holix -p shared telegram setup
```

The wizard validates the token via the Telegram API (`getMe`), saves it to **`~/.holix/profiles/<name>/telegram.env`**, and enables **access-request mode** (`HOLIX_TELEGRAM_ACCESS_REQUESTS=true`). You do **not** enter user ids during setup.

Use a **named** profile (`-p shared`) for production multi-user bots — profile `default` is dev-only when `HOLIX_ENV=production`.

### 9.4. Designate the Telegram admin (once, CLI only)

```bash
holix -p shared telegram requests approve USER_ID --set-admin
```

Creates Holix profile **`admin`**, stores the single admin in `telegram.env`, and enables the command menu for that user. Cannot be done from Telegram. Check: `holix telegram admin show`.

### 9.5. Users request access

1. User opens the bot in Telegram and sends **`/start`**.
2. Bot replies that access is pending (slash menu hidden).
3. The Telegram admin receives a notification with CLI approve/reject commands.

### 9.5.1. Admin approves and creates an isolated profile

```bash
holix -p shared telegram requests list
holix -p shared telegram requests approve USER_ID -i
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

Holix creates a **protected** profile (with `--create-profile`), enables **workspace jail**, binds the user, **sends the access key in Telegram**, and enables the slash menu. No bot restart required.

> **What users see:** when the agent mentions files, replies show paths **relative to the user's workspace folder** (for example `notes.txt` or `docs/report.pdf`), not the full server path under `~/.holix/profiles/…`. This is intentional privacy for multi-user hosts. Platform admins see full paths — [PROFILES.md](PROFILES.md#path-visibility-in-responses).

Other options: `requests approve … --profile existing`, `requests reject USER_ID`.  
Manual bindings: `holix telegram map set …` — see [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

### 9.6. Start the bot

**Standalone:**

```bash
holix telegram run
# or simply:
holix telegram
```

**Together with the API gateway** (recommended for always-on use):

```bash
HOLIX_ENV=production holix -p shared gateway start -f
```

The gateway supervisor also starts Telegram if it is configured.

### 9.7. Update the Telegram command menu

```bash
holix telegram sync-menu
```

Refreshes menus for **authorized** users only (hidden until approve). Run after changing skills, MCP, or slash commands.

### 9.8. Voice messages (optional)

If chat already goes through LiteLLM, configure the transcription model **in the LiteLLM config** and in the profile `.env`:

```bash
HOLIX_WHISPER_BASE_URL=http://localhost:4000/v1
HOLIX_WHISPER_API_KEY=sk-...          # LiteLLM virtual key
HOLIX_WHISPER_MODEL=whisper           # model_name from LiteLLM (not whisper-1)
HOLIX_TELEGRAM_VOICE_LANGUAGE=en
```

More details: [TELEGRAM.md](TELEGRAM.md).

### 9.8. Production

When `HOLIX_ENV=production`:

- use a **named** bot profile (`-p shared`), not `default`;
- prefer **access requests** (`telegram setup` + `telegram requests approve --create-profile`);
- or set `HOLIX_TELEGRAM_ALLOWED_USERS` for a personal single-user bot.

Full guide: [TELEGRAM.md](TELEGRAM.md).

---

## 10. Step 8 — Execution Modes

Holix supports four execution modes in TUI and Telegram:

| Mode | Name | When to use |
|------|------|-------------|
| **ReAct** | `react` | Quick questions, tools, exploration (default) |
| **Plan** | `plan_and_execute` | Multi-step tasks with clear subgoals |
| **Hybrid** | `hybrid` | Large tasks: plan first, flexible work per step |
| **Auto** | `auto` | Holix picks the best mode via a classifier |

Switch with **`/mode`** or **`/mode <name>`**. Plan modes use `/plan-confirm`, `/plan-auto`, `/plan-refine`, `/plan-reject`. Risky tools use `/yes`, `/1`–`/4`.

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
holix mcp list-popular
```

Examples from the catalog: `filesystem`, `github`, `context7`, `compass`, `postgres`, …

### 12.2. Install MCP (easy way)

```bash
holix mcp install
```

Interactive: pick from the list → enter parameters (paths, API keys) → test → save to profile.

Or by name:

```bash
holix mcp install context7
holix mcp install filesystem
```

From git:

```bash
holix mcp install https://github.com/upstash/context7
```

### 12.3. Assign MCP to agents

```bash
holix mcp assign
```

For example: `main` sees `filesystem` and `context7`, subagent `researcher` — only `context7`.

Verify:

```bash
holix mcp list
holix mcp test <server-name>
holix mcp tools
```

### 12.4. Full wizard

```bash
holix mcp setup
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
holix gateway reload
```

MCP tools in the agent are named **`mcp_<server>_<tool>`**.

### 12.7. Environment variables for MCP

Secrets in MCP config: `${GITHUB_TOKEN}`, `${CONTEXT7_API_KEY}`, etc.  
Values go in `~/.holix/.env`.  
`holix doctor` warns about unresolved `${VAR}`.

---

## 13. Step 11 — Skills and Hub Plugins

### 13.1. What are skills

A **skill** is a `SKILL.md` file with instructions for the agent.  
Stored in: `~/.holix/profiles/<profile>/data/skills/`

### 13.2. Install from Hub (CLI)

```bash
# search
holix hub search "docker" -s clawhub
holix hub search "git" -s clawhub

# interactive browse
holix hub browse

# install
holix hub install <spec>
holix hub install <spec> --agents main,coder
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
holix skills list --agent main
holix skills assign docker-manager --agents main,coder
holix skills unassign docker-manager --agent coder
holix skills assign-wizard    # interactive
```

### 13.5. Hub updates

```bash
holix hub list
holix hub check-updates
holix hub update
holix hub autoupdate --enable
holix hub slash-sync          # refresh skill-slash.json
```

### 13.6. Apply

```bash
holix gateway reload
```

---

## 14. CLI Reference

Global options: **`--profile` / `-p`**, **`--verbose` / `-v`**.

### Main commands

| Command | Purpose |
|---------|---------|
| `holix tui` | Full-screen interface (recommended) |
| `holix chat-command` | Terminal chat |
| `holix run "query"` | Single request without entering chat |
| `holix status` | Profile status |
| `holix version` | Version |
| `holix clear` | Clear profile data |
| `holix doctor` | Diagnostics |
| `holix install` | Install holix to PATH (from source) |
| `holix update` | Update |

### `holix models`

| Subcommand | Description |
|------------|-------------|
| `setup` | Interactive wizard |
| `add <preset>` | Add provider (`litellm`, `ollama`, …) |
| `presets` | List presets |
| `list` | Providers in profile |
| `agents` | Model assignments per agent |

### `holix config`

| Subcommand | Description |
|------------|-------------|
| `show` | Show YAML |
| `edit` | Editor |
| `set key value` | Change a field |

### `holix mcp`

`list`, `add`, `remove`, `test`, `assign`, `setup`, `list-popular`, `install`

### `holix hub`

`search`, `browse`, `install`, `list`, `remove`, `check-updates`, `update`, `autoupdate`, `slash-sync`

### `holix skills`

`list`, `search`, `show`, `assign`, `unassign`, `agents`, `assign-wizard`

### `holix memory`

`search "<query>"`

### `holix search`

`configure`, `list`, `test`

### `holix gateway`

`start`, `stop`, `status`, `reload`  
Endpoints: `/health`, `/v1/chat/completions`, … — see [GATEWAY.md](GATEWAY.md).

### `holix cron`

Requires a running gateway.  
`add`, `list`, `enable`, `disable`, `remove`

### `holix logs`

`holix logs`, `holix logs -f`, `holix logs -s agent`, `holix logs list`, `holix logs rotate`, `holix logs debug on`

### `holix telegram`

`setup`, `admin show|clear`, `requests list|approve|reject` (`--set-admin`, `-i`), `run`, `status`, `sync-menu`, `map set|list|remove|bind|import` — see [TELEGRAM.md](TELEGRAM.md) and [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md)

---

## 15. Slash Commands `/` in Chat

Work in **TUI**, **Telegram**, and partially in **`holix chat-command`**.

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

## 16. Holix Features

1. **Profiles** — multiple isolated configurations (`holix -p name`).
2. **Memory** — conversations + long-term memory + semantic search (`/memory`).
3. **Confirmations** — dangerous tool calls require explicit approval.
4. **Plan review** — multi-step tasks are not run silently without your OK (when enabled).
5. **Subagents** — background worker processes; main chat is not blocked (`/subagent-spawn`).
6. **MCP and Hub** — extend without editing agent code.
7. **Multi-interface** — one profile for TUI, Telegram, and API gateway.
8. **Logs** — structured logs for agent/gateway/cron/subagent (`holix logs`).
9. **Doctor** — self-diagnostics for the environment.
10. **OpenAI-compatible API** — gateway for integration with other clients.
11. **Voice in Telegram** — Whisper via LiteLLM, OpenAI, or locally (`faster-whisper`).
12. **Context compression** — `/compress` when the model window overflows.

---

## 17. Troubleshooting

```bash
holix doctor
holix doctor --fix
holix logs -l error -n 50
```

| Problem | What to check |
|---------|---------------|
| `holix: command not found` | PATH, venv, `pipx` / `uv tool` |
| No response from model | `LITELLM_API_KEY`, URL, `holix models list`, curl `/v1/models` |
| MCP not showing up | `holix mcp test`, `holix gateway reload`, `holix doctor` |
| Telegram silent | `holix telegram status`, token, `telegram requests list`, `holix gateway status` |
| Stale slash commands | `holix telegram sync-menu`, `holix gateway reload` |

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DOCTOR.md](DOCTOR.md).

---

## Quick checklist: from zero to chat

1. Python 3.12+  
2. `uv` or `pip`  
3. `uv pip install holix-….whl` (or `pipx install …`)  
4. `~/.holix/.env` with `LITELLM_API_BASE` and `LITELLM_API_KEY`  
5. `holix models add litellm --host http://localhost:4000`  
6. `holix models setup` → assign a model for `main`  
7. `holix doctor`  
8. `holix tui` or `holix telegram setup` + `holix gateway start`  
9. As needed: `holix mcp install`, `holix hub browse`, `holix search configure`  

---

## See also

- [INSTALLATION.md](INSTALLATION.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [CLI.md](CLI.md)
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md)
- [TELEGRAM.md](TELEGRAM.md)
- [HUB.md](HUB.md)
- [GATEWAY.md](GATEWAY.md)