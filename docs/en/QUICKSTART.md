# Quickstart

## Install (PyPI)

```bash
pipx install HelixAgentAi
# or: pip install HelixAgentAi  (inside an activated venv)
```

Package: [HelixAgentAi on PyPI](https://pypi.org/project/HelixAgentAi/). CLI command: `helix`.

## Run

```bash
helix doctor
helix models setup
helix run "Hello"
helix tui              # primary UI; /help for slash commands
helix gateway start
helix gateway status
helix logs -l error
```

Repair config:

```bash
helix doctor --fix
```

Optional extras:

```bash
pipx install "HelixAgentAi[all]"
helix -p shared telegram setup
helix -p shared gateway start
# users: /start → helix -p shared telegram requests approve USER_ID --create-profile NAME
playwright install chromium   # after [browser] extra
helix hub browse
helix mcp setup
```

Update from PyPI:

```bash
helix update --channel pypi
```

See [CLI.md](CLI.md) and [SLASH_COMMANDS.md](SLASH_COMMANDS.md).