# Skill Hub

Установка скиллов и плагинов Claude Code из публичных каталогов в активный профиль.

Расположение данных:

- Бандлы: `{profile}/data/skills/_hub/<slug>/`
- Lockfile: `{profile}/data/hub-lock.json`
- Плоские копии (опционально): `{profile}/data/skills/<name>.md`
- Slash-реестр: `{profile}/data/skills/skill-slash.json`

## CLI

```bash
helix hub search "git" -s clawhub
helix hub search "react" -s skills-sh
helix hub search "" -s hermes
helix hub browse                    # интерактивный выбор
helix hub install <spec>
helix hub install --agents main,coder
helix hub list
helix hub remove <lock-id>
helix hub check-updates
helix hub update                    # обновить ClawHub
helix hub autoupdate --enable       # фоновая политика в профиле
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
helix tui
```

В TUI:

| Действие | Команда / UI |
|--------|----------------|
| Выбор каталога | `/hub` |
| Установленное | `/hub installed` или режим **Installed** |
| Поиск и установка | `/hub browse` → Search → Install |
| Удалить hub-бандл | Installed → строка (hub) → **Remove hub** или Delete |
| Браузер | `helix tui --web` → http://127.0.0.1:8787 |

## Скиллы по агентам

Поле профиля `skill_assignments` ограничивает, какие скиллы видит каждый агент/субагент.

```bash
helix skills list --agent main
helix skills assign my-skill --agents main,coder
helix skills unassign my-skill --agent coder
helix hub install <spec> --agents main
```

В frontmatter скилла можно указать `agents:` / `agent_roles:`.

## MCP и переменные окружения

`${VAR}` и `${ENV:VAR}` в MCP плагинов подставляются при загрузке.  
`helix doctor` предупреждает `mcp.unresolved_env`, если переменных нет.