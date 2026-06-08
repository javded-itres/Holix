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

## Typical multi-user setup

```bash
# Alice — developer, full filesystem
helix -p alice profile env --edit
helix -p alice telegram setup
helix -p alice gateway start

# Bob — restricted to project folder
helix -p bob profile env --edit
helix -p bob profile jail enable /home/bob/projects
helix -p bob telegram setup
helix -p bob gateway start
```

## CLI reference

| Command | Description |
|---------|-------------|
| `helix -p <name> …` | Select profile (omit for `default`) |
| `helix profile env` | Show profile `.env` |
| `helix profile env --edit` | Edit secrets and gateway bind |
| `helix profile jail enable <path>` | Enable directory isolation |
| `helix profile jail disable` | Disable jail |
| `helix profile jail status` | Show jail settings |
| `helix status` | List profiles and active one |

In TUI/chat: `/profile <name>` to switch.

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