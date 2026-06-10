# Быстрый старт

## Установка (PyPI)

```bash
pipx install HelixAgentAi
# или: pip install HelixAgentAi  (в активированном venv)
```

Пакет: [HelixAgentAi на PyPI](https://pypi.org/project/HelixAgentAi/). Команда: `helix`.

## Запуск

```bash
helix doctor
helix models setup
helix run "Привет"
helix tui
helix gateway start
helix gateway status
helix logs -l error
helix doctor --fix
```

Опции:

```bash
pipx install "HelixAgentAi[all]"
helix -p shared telegram setup
helix -p shared gateway start
# пользователи: /start → helix -p shared telegram requests approve USER_ID --create-profile NAME
playwright install chromium
helix hub browse
helix mcp setup
```

Обновление с PyPI:

```bash
helix update --channel pypi
```

См. [CLI.md](CLI.md) и [SLASH_COMMANDS.md](SLASH_COMMANDS.md).