# Быстрый старт

## Установка

**Одной командой (macOS/Linux):**

```bash
curl -fsSL https://raw.githubusercontent.com/javded-itres/Holix/main/scripts/install.sh | bash
```

**Или вручную с PyPI:**

```bash
pipx install Holix
holix bootstrap
# или: pip install Holix  (в активированном venv)
```

Пакет: [Holix на PyPI](https://pypi.org/project/Holix/). Команда: `holix`. Подробнее: [INSTALLATION.md](INSTALLATION.md).

## Запуск

```bash
holix doctor
holix models setup
holix run "Привет"
holix tui
holix gateway start
holix gateway status
holix logs -l error
holix doctor --fix
```

Опции:

```bash
pipx install "Holix[all]"
holix -p shared telegram setup
holix -p shared gateway start
# пользователи: /start → holix -p shared telegram requests approve USER_ID --create-profile NAME
playwright install chromium
holix hub browse
holix mcp setup
```

Обновление с PyPI:

```bash
holix update --channel pypi
```

См. [CLI.md](CLI.md) и [SLASH_COMMANDS.md](SLASH_COMMANDS.md).