# Быстрый старт

## Установка (PyPI)

```bash
pipx install HelixAgentAi
# или: pip install HelixAgentAi  (в активированном venv)
```

Пакет: [HolixAgentAi на PyPI](https://pypi.org/project/HelixAgentAi/). Команда: `holix`.

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
pipx install "HelixAgentAi[all]"
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