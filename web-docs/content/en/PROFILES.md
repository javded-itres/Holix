# Profiles & isolation

Holix **profiles** are fully isolated agent environments on one machine. Each profile has its own configuration, secrets, memory, Telegram bot, and API gateway — so different people or projects do not interfere with each other.

### Profile `default` (development only)

In **development** (`HOLIX_ENV` not `production`), you can omit `-p` — Holix uses profile `default`:

```bash
holix gateway start
holix profile env --edit
```

In **production**, profile `default` is **not available**. Always pass a named profile:

```bash
HOLIX_ENV=production holix -p shared gateway start
HOLIX_ENV=production holix -p alice profile env --edit
```

## What is isolated per profile

| Resource | Path |
|----------|------|
| Profile access key (hash) | `~/.holix/profiles/<name>/profile.key` |
| Environment (API keys, ports) | `~/.holix/profiles/<name>/.env` |
| Telegram bot | `~/.holix/profiles/<name>/telegram.env` |
| API gateway state & log | `~/.holix/profiles/<name>/gateway/` |
| Models, MCP, skills config | `~/.holix/profiles/<name>/config.yaml` |
| Memory (SQLite + ChromaDB) | `~/.holix/profiles/<name>/data/memory/` |
| Skills | `~/.holix/profiles/<name>/data/skills/` |
| Cron jobs | `~/.holix/profiles/<name>/data/cron/` |
| Agent soul | `~/.holix/profiles/<name>/SOUL.md` |
| User profile | `~/.holix/profiles/<name>/USER.md` |
| First-run marker | `~/.holix/profiles/<name>/INIT.md` (removed after onboarding) |

Global under `~/.holix/`:

| Path | Purpose |
|------|---------|
| `global/config.yaml` | Shared models, MCP, search, behavior |
| `global/.env` | Shared API keys, voice, tool flags |
| `logs/`, MCP clones | Operational shared data |

Profiles **inherit** global settings by default. Per-profile files store **overrides only** — change a model in one profile without touching global; change global and all inheriting profiles update automatically.

```bash
holix profile global edit                 # edit shared settings
holix profile create team-a               # inherits global (default)
holix profile create team-b --clean       # empty profile, configure manually
holix -p team-a config set model smart    # override model for one profile only
```

Telegram tokens, memory, and gateway state remain **per profile** (not inherited).

## Agent identity (SOUL, INIT, USER)

Each profile can persist **who the agent is** and **who the user is** across sessions.

| File | Purpose |
|------|---------|
| `SOUL.md` | Agent personality, values, tone, and behavior |
| `USER.md` | Stable facts about the human (name, work style, language, notes) |
| `INIT.md` | First-run marker — while present, Holix runs a short onboarding chat |

When you run `holix profile create <name>`, Holix creates `INIT.md` and a placeholder `SOUL.md`.

### First conversation (onboarding)

While `INIT.md` exists, the agent:

1. Introduces itself and learns how you prefer to work together.
2. Saves facts with `save_user_profile` → `USER.md` + long-term memory.
3. Saves personality with `save_agent_soul` → `SOUL.md` (write or append).
4. Finishes with `complete_agent_initialization` — removes `INIT.md`.

You can say things like “save this as your personality” or “remember my name is …” in chat or Telegram; the agent picks the right tool. Match your language — Russian and English work.

### Every session

- **SOUL** is injected as a pinned system message at the start of each conversation and **re-applied after context compression** so personality is never lost.
- **USER** is included in the system prompt when `USER.md` exists.

Edit the files directly anytime:

```bash
holix -p alice profile env --edit   # secrets only
# identity files:
nano ~/.holix/profiles/alice/SOUL.md
nano ~/.holix/profiles/alice/USER.md
```

To reset onboarding for a profile, recreate `INIT.md` manually or run `holix profile create` on a new profile.

## Multiple gateways and Telegram bots

Run several gateways on different ports — one per profile:

```bash
# profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# profiles/bob/.env
HOLIX_GATEWAY_PORT=8002

holix -p alice gateway start
holix -p bob gateway start
```

Each profile can use a **different Telegram bot**:

```bash
holix -p alice telegram setup
holix -p bob telegram setup
```

### One bot for multiple users

**Recommended** — access requests + per-user protected profiles:

```bash
holix -p shared telegram setup
HOLIX_ENV=production holix -p shared gateway start -f
# users send /start; admin approves:
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

Each approved user gets a protected profile, workspace jail, and the access key in Telegram.

Manual bindings (`holix telegram map`) are still supported. See [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

## Workspace jail (directory isolation)

**Workspace jail** restricts file and terminal tools to a single directory tree. The agent cannot read, write, or run commands outside that folder — but works freely inside it.

**Automatic:** when you create a **protected** profile (`--protect`, `profile key init`, or `telegram requests approve --create-profile`), Holix creates:

`~/.holix/profiles/<name>/workspace/`

and enables jail pointing at that directory.

**Manual** (any profile):

```bash
holix profile jail enable ~/data-agent
holix profile jail status
holix profile jail disable
```

Or in `config.yaml`:

```yaml
workspace_jail_enabled: true
workspace_root: /home/user/data-agent
```

When enabled, these tools are scoped to `workspace_root`:

- `read_file`, `write_file`, `list_directory`
- `run_terminal_command` (working directory = jail root)
- Telegram file delivery from local paths

Holix internal data (memory, skills under `~/.holix/profiles/`) is **not** affected — jail applies to agent file/terminal tools only.

## Terminal whitelist (optional)

Control which shell commands the agent may run. Settings are stored per profile in `.env`.

```bash
holix -p dev profile whitelist enable
holix -p dev profile whitelist add "docker, make"
holix -p dev profile whitelist list
```

Persisted variables:

```bash
HOLIX_TERMINAL_COMMAND_WHITELIST=true
HOLIX_TERMINAL_WHITELIST_EXTRA=docker,make
```

Holix always applies a platform default set (`ls`, `git status`, `python`, `holix`, etc. on Unix; `dir`, `type`, `where` on Windows). Profile extras extend that list. Duplicate commands are ignored.

After changes, restart gateway/Telegram or re-run the CLI. See [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md) and [SECURITY.md](SECURITY.md).

## Profile access keys (optional)

By default, all profiles are **open** — you can switch by name only (`holix -p alice`, `/profile alice`).

Optionally, enable an **access key** (format `hp_…`) so only someone who knows the key can switch into that profile from the CLI, TUI, chat, or Telegram. The key is shown **once**; Holix stores only a hash in `~/.holix/profiles/<name>/profile.key`.

```bash
# Create a profile (open by default)
holix profile create alice
holix -p alice gateway start

# Create with key protection + workspace jail from the start
holix profile create bob --protect
# → ~/.holix/profiles/bob/workspace/ + profile.key (hp_…)

# Protect an existing open profile (also enables workspace jail)
holix -p alice profile key init

# Switch into a protected profile
holix -p bob --profile-key hp_xxxxxxxx
HOLIX_PROFILE_KEY=hp_xxxxxxxx holix -p bob

# Manage keys for the active profile
holix profile key status
holix profile key rotate    # replace key (requires current key)
holix profile key disable   # remove key — free switching by name again
```

To **turn off** key protection and switch freely (by profile name only):

```bash
holix -p alice --profile-key <current-key> profile key disable
# or when already inside the profile:
holix -p alice profile key disable
```

After `key disable`, the `profile.key` file is removed and `/profile alice` works without a key.

In interactive chat, TUI, or Telegram:

```text
/profile alice hp_xxxxxxxx
```

`holix status` lists profiles with access mode: `locked` (key required) or `open`.

For **systemd** and background workers, put the key in the profile `.env` so the service can start without a prompt:

```bash
# ~/.holix/profiles/alice/.env
HOLIX_PROFILE_KEY=hp_xxxxxxxx
```

The access key protects **switching into** a profile from Holix interfaces. It does not replace filesystem permissions on `~/.holix` or gateway API keys — see [SECURITY.md](SECURITY.md).

Telegram guide (one bot vs multiple bots): [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

## Typical multi-user setup

```bash
# Alice — developer, full filesystem
holix profile create alice
holix -p alice profile env --edit
holix -p alice telegram setup
holix -p alice gateway start

# Bob — restricted to project folder (optional key protection)
holix profile create bob --protect
holix -p bob --profile-key <key> profile env --edit
holix -p bob profile jail enable /home/bob/projects
holix -p bob telegram setup
holix -p bob gateway start
```

## CLI reference

| Command | Description |
|---------|-------------|
| `holix -p <name> …` | Select profile (omit for `default`) |
| `holix --profile-key <key>` | Access key for a protected profile |
| `holix profile create <name>` | Create profile inheriting global settings (default) |
| `holix profile create <name> --clean` | Standalone profile without global inheritance |
| `holix profile create <name> --protect` | Create profile with access key |
| `holix profile global show` | Show shared global config |
| `holix profile global edit` | Edit `global/config.yaml` |
| `holix profile global edit --env` | Edit `global/.env` |
| `holix profile global init` | (Re)create global config from defaults or `--from-profile` |
| `holix profile key status` | Show whether active profile is protected |
| `holix profile key init` | Generate key for an existing open profile |
| `holix profile key rotate` | Replace access key |
| `holix profile key disable` | Remove key and allow free switching |
| `holix profile env` | Show profile `.env` |
| `holix profile env --edit` | Edit secrets and gateway bind |
| `holix profile jail enable <path>` | Enable directory isolation |
| `holix profile jail disable` | Disable jail |
| `holix profile jail status` | Show jail settings |
| `holix profile whitelist add "<cmds>"` | Add comma-separated terminal commands |
| `holix profile whitelist list` | Show whitelist status and effective commands |
| `holix profile whitelist enable` | Enable terminal whitelist enforcement |
| `holix status` | List profiles (`locked` / `open`) and active one |

In TUI/chat/Telegram: `/profile <name> <access-key>` to switch into a protected profile.

## systemd

One gateway instance per profile. Use the template unit `holix-gateway@<name>`:

```bash
sudo systemctl enable --now holix-gateway@alice
sudo systemctl enable --now holix-gateway@bob
```

Profile `default`: `holix-gateway.service`. Secrets in `profiles/<name>/.env`, not `/etc/holix/`.

Full setup: [DEPLOYMENT.md](DEPLOYMENT.md#systemd).

## Related

- [CONFIGURATION.md](CONFIGURATION.md) — env layers and YAML
- [GATEWAY.md](GATEWAY.md) — per-profile gateway
- [TELEGRAM.md](TELEGRAM.md) — per-profile bot
- [CLI.md](CLI.md) — full command reference
- [SECURITY.md](SECURITY.md) — auth, confirmations, production