# Quickstart

## Install

**One line (recommended on macOS/Linux):**

```bash
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
```

**Or PyPI manually:**

```bash
pipx install Holix
holix bootstrap
# or: pip install Holix  (inside an activated venv)
```

Package: [Holix on PyPI](https://pypi.org/project/Holix/). CLI command: `holix`. Details: [INSTALLATION.md](INSTALLATION.md).

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
pipx install "Holix[all]"
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