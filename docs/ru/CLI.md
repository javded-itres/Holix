# Справочник CLI

Точка входа: **`helix`** (Typer).

## Глобальные опции

| Опция | Кратко | По умолчанию | Описание |
|-------|--------|--------------|----------|
| `--profile` | `-p` | `default` | Профиль в `~/.helix/profiles/<имя>/` |
| `--verbose` | `-v` | выкл | Подробный вывод |

Для профиля **default** флаг `-p` не нужен:

```bash
helix gateway start          # то же, что helix -p default gateway start
helix -p work status         # -p только для других профилей
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
| `profile` | `.env` профиля и workspace jail |
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

## `helix profile`

Изоляция профиля: env-файл и опциональный workspace jail.

| Подкоманда | Описание |
|------------|----------|
| `env` | Показать `.env` профиля |
| `env --edit` | Открыть `profiles/<имя>/.env` в `$EDITOR` |
| `jail enable <path>` | Ограничить файловые/терминальные инструменты одной директорией |
| `jail disable` | Выключить jail |
| `jail status` | Статус jail |

```bash
helix -p alice profile env --edit
helix -p data-agent profile jail enable ~/data-agent
```

[CONFIGURATION.md](CONFIGURATION.md)

---

## `helix gateway`

Привязан к **активному профилю** (`-p`). Несколько gateway на разных портах.

| Подкоманда | Описание |
|------------|----------|
| `start` | Фоновый запуск |
| `stop` | Остановка gateway этого профиля |
| `status` | Статус этого профиля |
| `reload` | Перезапуск |

```bash
helix -p alice gateway start -f
```

Состояние: `profiles/<имя>/gateway/state.json` · [GATEWAY.md](GATEWAY.md)

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

Токен бота хранится в `profiles/<имя>/telegram.env`.

```bash
helix -p alice telegram setup
helix -p alice telegram run
helix -p alice telegram sync-menu
```

[TELEGRAM.md](TELEGRAM.md)

---

## Профили

| Путь | Содержимое |
|------|------------|
| `~/.helix/profiles/<имя>/.env` | Ключи API, порт gateway, флаги |
| `~/.helix/profiles/<имя>/telegram.env` | Токен бота и allowlist |
| `~/.helix/profiles/<имя>/gateway/` | Состояние и лог gateway |
| `~/.helix/profiles/<имя>/config.yaml` | Модели, MCP, workspace jail |
| `.../data/memory/` | SQLite + ChromaDB |
| `.../data/skills/` | Навыки |

```bash
helix -p staging tui
helix -p staging profile jail enable ~/staging-workspace
```

---

## См. также

- [SLASH_COMMANDS.md](SLASH_COMMANDS.md)
- [INSTALLATION.md](INSTALLATION.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [LOGS.md](LOGS.md)
- Полная английская версия: [../en/CLI.md](../en/CLI.md)