# Skill Hub

Установка скиллов и плагинов Claude Code из публичных каталогов в активный профиль.

Расположение данных:

- Бандлы: `{profile}/data/skills/_hub/<slug>/`
- Lockfile: `{profile}/data/hub-lock.json`
- Плоские копии (опционально): `{profile}/data/skills/<name>.md`
- Slash-реестр: `{profile}/data/skills/skill-slash.json`

## CLI

```bash
holix hub search "git" -s clawhub
holix hub search "react" -s skills-sh
holix hub search "" -s hermes
holix hub browse                    # интерактивный выбор
holix hub install <spec>
holix hub install --agents main,coder
holix hub list
holix hub remove <lock-id>
holix hub check-updates
holix hub update                    # обновить ClawHub
holix hub autoupdate --enable       # фоновая политика в профиле
```

### Форматы установки

| Префикс | Пример |
|--------|---------|
| ClawHub | `my-skill` или `clawhub:slug@1.0` |
| Claude plugin | `claude:github@claude-official` |
| Hermes | `hermes:api-builder` |
| skills.sh | `skills-sh/owner/repo/path` |
| Git | `git:https://github.com/...` |
| Локально | путь к `SKILL.md` или бандлу |

У плагинов Claude могут быть MCP-серверы; `--with-mcp` (по умолчанию) добавляет их в `mcp_servers`.

## TUI

```bash
uv sync --extra tui-web    # опционально: режим браузера
holix tui
```

В TUI:

| Действие | Команда / UI |
|--------|----------------|
| Выбор каталога | `/hub` |
| Установленное | `/hub installed` или режим **Installed** |
| Поиск и установка | `/hub browse` → Search → Install |
| Удалить hub-бандл | Installed → строка (hub) → **Remove hub** или Delete |
| Браузер | `holix tui --web` → http://127.0.0.1:8787 |

## Скиллы по агентам

Поле профиля `skill_assignments` ограничивает, какие скиллы видит каждый агент/субагент.

```bash
holix skills list --agent main
holix skills assign my-skill --agents main,coder
holix skills unassign my-skill --agent coder
holix hub install <spec> --agents main
```

В frontmatter скилла можно указать `agents:` / `agent_roles:`.

## MCP и переменные окружения

`${VAR}` и `${ENV:VAR}` в MCP плагинов подставляются при загрузке.  
`holix doctor` предупреждает `mcp.unresolved_env`, если переменных нет.