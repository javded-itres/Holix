# Profiles & isolation

Helix **profiles** are fully isolated agent environments on one machine. Each profile has its own configuration, secrets, memory, Telegram bot, and API gateway — so different people or projects do not interfere with each other.

### Profile `default` (development only)

In **development** (`HELIX_ENV` not `production`), you can omit `-p` — Helix uses profile `default`:

```bash
helix gateway start
helix profile env --edit
```

In **production**, profile `default` is **not available**. Always pass a named profile:

```bash
HELIX_ENV=production helix -p shared gateway start
HELIX_ENV=production helix -p alice profile env --edit
```

## What is isolated per profile

| Resource | Path |
|----------|------|
| Profile access key (hash) | `~/.helix/profiles/<name>/profile.key` |
| Environment (API keys, ports) | `~/.helix/profiles/<name>/.env` |
| Telegram bot | `~/.helix/profiles/<name>/telegram.env` |
| API gateway state & log | `~/.helix/profiles/<name>/gateway/` |
| Models, MCP, skills config | `~/.helix/profiles/<name>/config.yaml` |
| Memory (SQLite + ChromaDB) | `~/.helix/profiles/<name>/data/memory/` |
| Skills | `~/.helix/profiles/<name>/data/skills/` |
| Cron jobs | `~/.helix/profiles/<name>/data/cron/` |

Global under `~/.helix/`:

| Path | Purpose |
|------|---------|
| `global/config.yaml` | Shared models, MCP, search, behavior |
| `global/.env` | Shared API keys, voice, tool flags |
| `logs/`, MCP clones | Operational shared data |

Profiles **inherit** global settings by default. Per-profile files store **overrides only** — change a model in one profile without touching global; change global and all inheriting profiles update automatically.

```bash
helix profile global edit                 # edit shared settings
helix profile create team-a               # inherits global (default)
helix profile create team-b --clean       # empty profile, configure manually
helix -p team-a config set model smart    # override model for one profile only
```

Telegram tokens, memory, and gateway state remain **per profile** (not inherited).

## Multiple gateways and Telegram bots

Run several gateways on different ports — one per profile:

```bash
# profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# profiles/bob/.env
HELIX_GATEWAY_PORT=8002

helix -p alice gateway start
helix -p bob gateway start
```

Each profile can use a **different Telegram bot**:

```bash
helix -p alice telegram setup
helix -p bob telegram setup
```

### One bot for multiple users

**Recommended** — access requests + per-user protected profiles:

```bash
helix -p shared telegram setup
HELIX_ENV=production helix -p shared gateway start -f
# users send /start; admin approves:
helix -p shared telegram requests approve USER_ID --create-profile ivan
```

Each approved user gets a protected profile, workspace jail, and the access key in Telegram.

Manual bindings (`helix telegram map`) are still supported. See [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

## Workspace jail (directory isolation)

**Workspace jail** restricts file and terminal tools to a single directory tree. The agent cannot read, write, or run commands outside that folder — but works freely inside it.

**Automatic:** when you create a **protected** profile (`--protect`, `profile key init`, or `telegram requests approve --create-profile`), Helix creates:

`~/.helix/profiles/<name>/workspace/`

and enables jail pointing at that directory.

**Manual** (any profile):

```bash
helix profile jail enable ~/data-agent
helix profile jail status
helix profile jail disable
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

Helix internal data (memory, skills under `~/.helix/profiles/`) is **not** affected — jail applies to agent file/terminal tools only.

## Terminal whitelist (optional)

Control which shell commands the agent may run. Settings are stored per profile in `.env`.

```bash
helix -p dev profile whitelist enable
helix -p dev profile whitelist add "docker, make"
helix -p dev profile whitelist list
```

Persisted variables:

```bash
HELIX_TERMINAL_COMMAND_WHITELIST=true
HELIX_TERMINAL_WHITELIST_EXTRA=docker,make
```

Helix always applies a platform default set (`ls`, `git status`, `python`, `helix`, etc. on Unix; `dir`, `type`, `where` on Windows). Profile extras extend that list. Duplicate commands are ignored.

After changes, restart gateway/Telegram or re-run the CLI. See [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md) and [SECURITY.md](SECURITY.md).

## Profile access keys (optional)

By default, all profiles are **open** — you can switch by name only (`helix -p alice`, `/profile alice`).

Optionally, enable an **access key** (format `hp_…`) so only someone who knows the key can switch into that profile from the CLI, TUI, chat, or Telegram. The key is shown **once**; Helix stores only a hash in `~/.helix/profiles/<name>/profile.key`.

```bash
# Create a profile (open by default)
helix profile create alice
helix -p alice gateway start

# Create with key protection + workspace jail from the start
helix profile create bob --protect
# → ~/.helix/profiles/bob/workspace/ + profile.key (hp_…)

# Protect an existing open profile (also enables workspace jail)
helix -p alice profile key init

# Switch into a protected profile
helix -p bob --profile-key hp_xxxxxxxx
HELIX_PROFILE_KEY=hp_xxxxxxxx helix -p bob

# Manage keys for the active profile
helix profile key status
helix profile key rotate    # replace key (requires current key)
helix profile key disable   # remove key — free switching by name again
```

To **turn off** key protection and switch freely (by profile name only):

```bash
helix -p alice --profile-key <current-key> profile key disable
# or when already inside the profile:
helix -p alice profile key disable
```

After `key disable`, the `profile.key` file is removed and `/profile alice` works without a key.

In interactive chat, TUI, or Telegram:

```text
/profile alice hp_xxxxxxxx
```

`helix status` lists profiles with access mode: `locked` (key required) or `open`.

For **systemd** and background workers, put the key in the profile `.env` so the service can start without a prompt:

```bash
# ~/.helix/profiles/alice/.env
HELIX_PROFILE_KEY=hp_xxxxxxxx
```

The access key protects **switching into** a profile from Helix interfaces. It does not replace filesystem permissions on `~/.helix` or gateway API keys — see [SECURITY.md](SECURITY.md).

Telegram guide (one bot vs multiple bots): [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

## Typical multi-user setup

```bash
# Alice — developer, full filesystem
helix profile create alice
helix -p alice profile env --edit
helix -p alice telegram setup
helix -p alice gateway start

# Bob — restricted to project folder (optional key protection)
helix profile create bob --protect
helix -p bob --profile-key <key> profile env --edit
helix -p bob profile jail enable /home/bob/projects
helix -p bob telegram setup
helix -p bob gateway start
```

## CLI reference

| Command | Description |
|---------|-------------|
| `helix -p <name> …` | Select profile (omit for `default`) |
| `helix --profile-key <key>` | Access key for a protected profile |
| `helix profile create <name>` | Create profile inheriting global settings (default) |
| `helix profile create <name> --clean` | Standalone profile without global inheritance |
| `helix profile create <name> --protect` | Create profile with access key |
| `helix profile global show` | Show shared global config |
| `helix profile global edit` | Edit `global/config.yaml` |
| `helix profile global edit --env` | Edit `global/.env` |
| `helix profile global init` | (Re)create global config from defaults or `--from-profile` |
| `helix profile key status` | Show whether active profile is protected |
| `helix profile key init` | Generate key for an existing open profile |
| `helix profile key rotate` | Replace access key |
| `helix profile key disable` | Remove key and allow free switching |
| `helix profile env` | Show profile `.env` |
| `helix profile env --edit` | Edit secrets and gateway bind |
| `helix profile jail enable <path>` | Enable directory isolation |
| `helix profile jail disable` | Disable jail |
| `helix profile jail status` | Show jail settings |
| `helix profile whitelist add "<cmds>"` | Add comma-separated terminal commands |
| `helix profile whitelist list` | Show whitelist status and effective commands |
| `helix profile whitelist enable` | Enable terminal whitelist enforcement |
| `helix status` | List profiles (`locked` / `open`) and active one |

In TUI/chat/Telegram: `/profile <name> <access-key>` to switch into a protected profile.

## systemd

One gateway instance per profile. Use the template unit `helix-gateway@<name>`:

```bash
sudo systemctl enable --now helix-gateway@alice
sudo systemctl enable --now helix-gateway@bob
```

Profile `default`: `helix-gateway.service`. Secrets in `profiles/<name>/.env`, not `/etc/helix/`.

Full setup: [DEPLOYMENT.md](DEPLOYMENT.md#systemd).

## Related

- [CONFIGURATION.md](CONFIGURATION.md) — env layers and YAML
- [GATEWAY.md](GATEWAY.md) — per-profile gateway
- [TELEGRAM.md](TELEGRAM.md) — per-profile bot
- [CLI.md](CLI.md) — full command reference
- [SECURITY.md](SECURITY.md) — auth, confirmations, production