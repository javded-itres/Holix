# Profiles & isolation

Helix **profiles** are fully isolated agent environments on one machine. Each profile has its own configuration, secrets, memory, Telegram bot, and API gateway — so different people or projects do not interfere with each other.

For the **default** profile you do not need `-p`:

```bash
helix gateway start
helix profile env --edit
```

Other profiles: `helix -p alice gateway start`.

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

Global under `~/.helix/`: shared logs, MCP server clones. Everything agent-specific lives under the profile.

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

## Workspace jail (directory isolation)

Optional **workspace jail** restricts file and terminal tools to a single directory tree. The agent cannot read, write, or run commands outside that folder — but works freely inside it.

Use cases:

- Give each user their own folder on a shared server
- Limit a data-analysis agent to `~/data-agent`
- Prevent accidental access to the rest of the filesystem

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

After changes, restart gateway/Telegram or re-run the CLI. See [SECURITY.md](SECURITY.md).

## Profile access keys (optional)

By default, all profiles are **open** — you can switch by name only (`helix -p alice`, `/profile alice`).

Optionally, enable an **access key** (format `hp_…`) so only someone who knows the key can switch into that profile from the CLI, TUI, chat, or Telegram. The key is shown **once**; Helix stores only a hash in `~/.helix/profiles/<name>/profile.key`.

```bash
# Create a profile (open by default)
helix profile create alice
helix -p alice gateway start

# Create with key protection from the start
helix profile create bob --protect

# Protect an existing open profile
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
| `helix profile create <name>` | Create profile (open by default) |
| `helix profile create <name> --protect` | Create profile with access key |
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