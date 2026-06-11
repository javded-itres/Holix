# Quickstart

## Install (PyPI)

```bash
pipx install HelixAgentAi
# or: pip install HelixAgentAi  (inside an activated venv)
```

Package: [HolixAgentAi on PyPI](https://pypi.org/project/HelixAgentAi/). CLI command: `holix`.

## Run

```bash
holix doctor
holix models setup
holix run "Hello"
holix tui              # primary UI; /help for slash commands
holix gateway start
holix gateway status
holix logs -l error
```

Repair config:

```bash
holix doctor --fix
```

Optional extras:

```bash
pipx install "HelixAgentAi[all]"
holix -p shared telegram setup
holix -p shared gateway start
# users: /start → holix -p shared telegram requests approve USER_ID --create-profile NAME
playwright install chromium   # after [browser] extra
holix hub browse
holix mcp setup
```

Update from PyPI:

```bash
holix update --channel pypi
```

See [CLI.md](CLI.md) and [SLASH_COMMANDS.md](SLASH_COMMANDS.md).