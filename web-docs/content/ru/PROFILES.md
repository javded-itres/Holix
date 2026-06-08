# Профили и изоляция

**Профили** Helix — полностью изолированные окружения агента на одной машине. У каждого профиля свои настройки, секреты, память, Telegram-бот и API gateway — разные люди или проекты не мешают друг другу.

Для профиля **default** флаг `-p` не нужен:

```bash
helix gateway start
helix profile env --edit
```

Другие профили: `helix -p alice gateway start`.

## Что изолировано в профиле

| Ресурс | Путь |
|--------|------|
| Окружение (ключи API, порты) | `~/.helix/profiles/<имя>/.env` |
| Telegram-бот | `~/.helix/profiles/<имя>/telegram.env` |
| Состояние и лог gateway | `~/.helix/profiles/<имя>/gateway/` |
| Модели, MCP, навыки | `~/.helix/profiles/<имя>/config.yaml` |
| Память (SQLite + ChromaDB) | `~/.helix/profiles/<имя>/data/memory/` |
| Навыки | `~/.helix/profiles/<имя>/data/skills/` |
| Cron-задачи | `~/.helix/profiles/<имя>/data/cron/` |

Глобально в `~/.helix/`: общие логи, клоны MCP-серверов. Всё, что относится к агенту — в каталоге профиля.

## Несколько gateway и Telegram-ботов

Несколько gateway на разных портах — по одному на профиль:

```bash
# profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# profiles/bob/.env
HELIX_GATEWAY_PORT=8002

helix -p alice gateway start
helix -p bob gateway start
```

У каждого профиля может быть **свой Telegram-бот**:

```bash
helix -p alice telegram setup
helix -p bob telegram setup
```

## Workspace jail (изоляция в директории)

Опциональный **workspace jail** ограничивает файловые и терминальные инструменты одной директорией. Агент не может читать, писать или выполнять команды за её пределами, но внутри работает без ограничений.

Сценарии:

- Отдельная папка каждому пользователю на общем сервере
- Агент анализа данных только в `~/data-agent`
- Защита от случайного доступа к остальной файловой системе

```bash
helix profile jail enable ~/data-agent
helix profile jail status
helix profile jail disable
```

Или в `config.yaml`:

```yaml
workspace_jail_enabled: true
workspace_root: /home/user/data-agent
```

При включении jail действует на:

- `read_file`, `write_file`, `list_directory`
- `run_terminal_command` (рабочая директория = корень jail)
- отправку файлов в Telegram с локальных путей

Внутренние данные Helix (память, навыки в `~/.helix/profiles/`) **не затрагиваются** — jail только для файловых и терминальных инструментов агента.

## Типичная настройка для нескольких пользователей

```bash
# Alice — разработчик, полный доступ к ФС
helix -p alice profile env --edit
helix -p alice telegram setup
helix -p alice gateway start

# Bob — только своя папка проекта
helix -p bob profile env --edit
helix -p bob profile jail enable /home/bob/projects
helix -p bob telegram setup
helix -p bob gateway start
```

## Справочник CLI

| Команда | Описание |
|---------|----------|
| `helix -p <имя> …` | Выбор профиля (для `default` не нужен) |
| `helix profile env` | Показать `.env` профиля |
| `helix profile env --edit` | Редактировать секреты и bind gateway |
| `helix profile jail enable <path>` | Включить изоляцию в директории |
| `helix profile jail disable` | Выключить jail |
| `helix profile jail status` | Статус jail |
| `helix status` | Список профилей и активный |

В TUI/чате: `/profile <имя>` для переключения.

## systemd

Один instance gateway на профиль. Шаблонный unit `helix-gateway@<имя>`:

```bash
sudo systemctl enable --now helix-gateway@alice
sudo systemctl enable --now helix-gateway@bob
```

Профиль `default`: `helix-gateway.service`. Секреты в `profiles/<имя>/.env`, не в `/etc/helix/`.

Полная инструкция: [DEPLOYMENT.md](DEPLOYMENT.md#systemd).

## См. также

- [CONFIGURATION.md](CONFIGURATION.md) — слои env и YAML
- [GATEWAY.md](GATEWAY.md) — gateway на профиль
- [TELEGRAM.md](TELEGRAM.md) — бот на профиль
- [CLI.md](CLI.md) — справочник команд
- [SECURITY.md](SECURITY.md) — auth, подтверждения, production