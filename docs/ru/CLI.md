# Справочник CLI

Точка входа: **`helix`** (Typer).

## Глобальные опции

| Опция | Кратко | По умолчанию | Описание |
|-------|--------|--------------|----------|
| `--profile` | `-p` | `default` | Профиль в `~/.helix/profiles/<имя>/` |
| `--verbose` | `-v` | выкл | Подробный вывод |

```bash
helix -p work status
```

## Команды верхнего уровня

| Команда | Назначение |
|---------|------------|
| `chat-command` | Интерактивный чат в терминале |
| `run` | Один запрос и выход |
| `tui` | Полноэкранный TUI (рекомендуется) |
| `status` | Статус профиля |
| `clear` | Очистить `data/` профиля |
| `version` | Версия |
| `skills` | Навыки |
| `memory` | Память |
| `config` | config.yaml |
| `models` | Провайдеры и маршрутизация |
| `telegram` | Telegram-бот |
| `gateway` | API gateway |
| `cron` | Планировщик задач (в gateway) |
| `logs` | Просмотр логов, ротация, debug |
| `doctor` | Диагностика |
| `mcp` | MCP-серверы |
| `hub` | Каталоги навыков |
| `install` | Установка в PATH |
| `update` | Обновление |

Слэш-команды: **[SLASH_COMMANDS.md](SLASH_COMMANDS.md)**.

---

## `helix chat-command`

```bash
helix chat-command
helix chat-command -m qwen2.5-coder:32b --max-steps 20
```

Опции: `--model`, `--temperature`, `--max-steps`.

Слэши: `/help`, `/exit`, `/clear`, `/model`, `/profile`, `/skills`, `/memory`, `/status`, `/metrics`, `/stream`, `/debug`, `/compress` — см. [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

---

## `helix run`

```bash
helix run "Кратко опиши репозиторий"
helix run "…" -c id_разговора
```

---

## `helix tui`

```bash
helix tui
helix tui --web
helix tui --web --allow-lan --token "$(openssl rand -hex 32)"
```

Legacy: `HELIX_TUI_LEGACY=1 helix tui`.  
Подробнее: [TUI.md](TUI.md).

---

## `helix status` / `clear` / `version`

- **status** — модель, URL, каталоги, список профилей  
- **clear** — удаление памяти и навыков (`-y` без подтверждения)  
- **version** — версия пакета  

---

## `helix install` / `update`

```bash
helix install
helix install --extra telegram
helix update --check
```

См. [INSTALLATION.md](INSTALLATION.md).

---

## `helix config`

| Подкоманда | Описание |
|------------|----------|
| `show` | YAML профиля |
| `edit` | Редактор `$EDITOR` |
| `set ключ значение` | Поле `ProfileConfig` |

---

## `helix models`

| Подкоманда | Описание |
|------------|----------|
| `setup` | Мастер провайдеров и `agent_models` |
| `list` | Список провайдеров |
| `agents` | Назначения по агентам |

```bash
helix models setup
```

---

## `helix skills`

| Подкоманда | Описание |
|------------|----------|
| `list` | Список (`--agent`) |
| `search` | Поиск |
| `show` | Текст навыка |
| `assign` / `unassign` | `skill_assignments` |
| `agents` | Какие агенты видят навык |
| `assign-wizard` | Интерактивное назначение |

---

## `helix memory`

`helix memory search "<запрос>"` — в TUI: `/memory <запрос>`.

---

## `helix gateway`

| Подкоманда | Описание |
|------------|----------|
| `start` | Фоновый запуск |
| `stop` | Остановка |
| `status` | Статус |
| `reload` | Перезапуск |

```bash
helix gateway start -f
```

[GATEWAY.md](GATEWAY.md)

---

## `helix cron`

```bash
helix gateway start
helix cron add "every day at 9 :: Проверить логи"
helix cron list
```

В TUI/Telegram: `/cron`, `/cron add …`. Лог запусков: `profiles/<p>/data/cron/runs.log`.

---

## `helix logs`

```bash
helix logs
helix logs -s agent -l error -n 100
helix logs -f
helix logs list
helix logs rotate
helix logs debug on
```

Источники `-s`: `all`, `agent`, `gateway`, `cron`, `subagent`, `system`.  
Опции: `-n`, `-l`, `-g`, `-f`, `--debug`, `-v`. Полная версия: [LOGS.md](LOGS.md).

---

## `helix doctor`

```bash
helix doctor
helix doctor --fix
helix doctor --no-llm
```

[DOCTOR.md](DOCTOR.md)

---

## `helix mcp`

| Подкоманда | Описание |
|------------|----------|
| `list` | Серверы |
| `add` / `remove` | Добавить / удалить |
| `test` | Проверка |
| `assign` / `setup` | Назначение агентам |
| `list-popular` / `install` | Быстрая установка |

Tools: `mcp_<сервер>_<имя>`. В TUI: `/mcp`.

---

## `helix hub`

| Подкоманда | Описание |
|------------|----------|
| `search` | Поиск в каталогах |
| `browse` | Интерактивная установка |
| `install` | Установка по spec |
| `list` / `remove` | Список / удаление |
| `check-updates` / `update` / `autoupdate` | Обновления |
| `slash-sync` | `skill-slash.json` |

[HUB.md](HUB.md)

---

## `helix telegram`

```bash
helix telegram setup
helix telegram run
helix telegram sync-menu
```

[TELEGRAM.md](TELEGRAM.md)

---

## Профили

| Путь | Содержимое |
|------|------------|
| `~/.helix/profiles/<имя>/config.yaml` | Настройки |
| `.../data/memory/` | SQLite + ChromaDB |
| `.../data/skills/` | Навыки |

```bash
helix -p staging tui
```

---

## См. также

- [SLASH_COMMANDS.md](SLASH_COMMANDS.md)
- [INSTALLATION.md](INSTALLATION.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [LOGS.md](LOGS.md)
- Полная английская версия: [../en/CLI.md](../en/CLI.md)