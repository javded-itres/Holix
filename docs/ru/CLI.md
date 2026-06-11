# Справочник CLI

Точка входа: **`helix`** (Typer).

## Глобальные опции

| Опция | Кратко | По умолчанию | Описание |
|-------|--------|--------------|----------|
| `--profile` | `-p` | *(dev: `default`)* | Профиль в `~/.helix/profiles/<имя>/` |
| `--profile-key` | | env `HELIX_PROFILE_KEY` | Ключ доступа к защищённому профилю |
| `--verbose` | `-v` | выкл | Подробный вывод |

В **development** можно не указывать `-p` — используется `default`. В **production** (`HELIX_ENV=production`) нужен **именованный** профиль — `default` недоступен:

```bash
helix gateway start
helix -p work status
HELIX_ENV=production helix -p shared gateway start
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
| `setup` | Мастер провайдеров, `agent_models`, fallback |
| `list` | Список провайдеров |
| `agents` | Назначения по агентам |
| `fallback list` | Цепочка fallback-провайдеров |
| `fallback set PROVIDERS` | Задать fallback (`litellm,ollama`) |
| `fallback clear` | Убрать fallback на уровне профиля |

```bash
helix models setup
helix models fallback set litellm,ollama
helix models fallback list
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

Изоляция профиля и **общие глобальные настройки** (наследуются по умолчанию).

| Подкоманда | Описание |
|------------|----------|
| `create <имя>` | Новый профиль (`--inherit` по умолчанию, `--clean` — без global) |
| `create <имя> --protect` | С ключом доступа + workspace jail |
| `global show` | Показать `~/.helix/global/config.yaml` |
| `global edit` | Редактировать global YAML (модели, MCP, поведение) |
| `global edit --env` | Редактировать `~/.helix/global/.env` |
| `global init` | (Пере)создать global (`--from-profile default`) |
| `env` | Показать `.env` профиля (переопределения) |
| `env --edit` | Открыть переопределения профиля в `$EDITOR` |
| `jail enable <path>` | Ограничить файловые/терминальные инструменты одной директорией |
| `jail disable` | Выключить jail |
| `jail status` | Статус jail |
| `whitelist add "<команды>"` | Добавить команды через запятую |
| `whitelist list` | Статус whitelist и итоговый список |
| `whitelist enable` | Включить проверку whitelist |

```bash
helix profile global edit
helix profile create team-a
helix profile create team-b --clean
helix -p alice profile env --edit
helix -p data-agent profile jail enable ~/data-agent
```

[CONFIGURATION.md](CONFIGURATION.md), [PROFILES.md](PROFILES.md)

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

### Ключи gateway API

**Нет** CLI-команды `helix` для создания ключей gateway (`hx_…`). Варианты:

```bash
# curl (нужен существующий admin hx_ key)
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys?name=my-app&permissions=read,write" \
  -H "Authorization: Bearer hx_admin_…"

# или Swagger UI после helix gateway start
open http://127.0.0.1:8000/docs   # Authorize → HelixApiKey → вставьте hx_…
```

**Ключи доступа к профилю** (`hp_…`) — другое назначение: защита переключения профиля и `/api/helix/*` management, не HTTP-поверхность gateway:

```bash
helix -p alice profile key init    # генерирует hp_… (показывается один раз)
helix -p alice --profile-key hp_…  # использование в CLI/TUI
```

Первый admin-ключ: временно `HELIX_REQUIRE_AUTH=false`, создайте через `POST /admin/api-keys`, затем включите auth. Полный справочник: [GATEWAY_API.md](GATEWAY_API.md).

---

## `helix docs`

Сайт документации (лендинг + SPA, поиск, EN/RU).

| Подкоманда | Описание |
|------------|----------|
| *(по умолчанию)* | Запуск на `127.0.0.1:8080` |
| `serve` | То же, что по умолчанию |
| `build` | Синхронизация `docs/en` + `docs/ru` → `web-docs/`, пересборка поиска и SEO |

```bash
helix docs build
helix docs --port 8080 --open
helix gateway start --with-docs
```

См. [DEPLOYMENT.md](DEPLOYMENT.md).

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

| Подкоманда | Описание |
|------------|----------|
| `setup` | Мастер: только токен бота; включает режим запросов доступа |
| `run` | Запуск polling (`-p` выбирает профиль бота) |
| `status` | Сохранённая конфигурация (токен скрыт), привязки |
| `sync-menu` | Обновить slash-меню **только для одобренных** (скрыто до approve) |
| `admin show` | Показать Telegram-администратора (назначается только из CLI) |
| `admin clear` | Сбросить админа перед повторным `--set-admin` |
| `requests list` | Ожидающие запросы после `/start` |
| `requests approve USER_ID` | Одобрить (`--create-profile`, `--profile`, `-i` или `--set-admin`) |
| `requests reject USER_ID` | Отклонить запрос |
| `map set USER_ID PROFILE` | Ручная привязка Telegram user id → профиль Helix |
| `map list` | Список привязок |
| `map remove USER_ID` | Удалить привязку |
| `map bind PROFILE` | Быстрая привязка (`--user-id` или id из allowlist) |
| `map import "ID:prof,..."` | Импорт нескольких привязок |

```bash
helix -p shared telegram setup
helix -p shared telegram requests approve 123456789 --set-admin   # первый админ + профиль admin
helix -p shared telegram requests list
helix -p shared telegram requests approve 123456789 --create-profile ivan
helix -p shared telegram admin show
helix -p shared telegram map set 123456789 alice   # ручная альтернатива
helix -p shared gateway start
```

Один бот на несколько изолированных профилей: [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).  
Общее: [TELEGRAM.md](TELEGRAM.md).

---

## Профили

| Путь | Содержимое |
|------|------------|
| `~/.helix/profiles/<имя>/.env` | Ключи API, порт gateway, флаги |
| `~/.helix/profiles/<имя>/telegram.env` | Токен бота, allowlist, `HELIX_TELEGRAM_USER_PROFILES` |
| `~/.helix/profiles/<имя>/telegram-users.json` | Привязки Telegram user id → профиль (общий бот) |
| `~/.helix/profiles/<имя>/gateway/` | Состояние и лог gateway |
| `~/.helix/profiles/<имя>/config.yaml` | Модели, MCP, workspace jail |
| `~/.helix/profiles/<имя>/SOUL.md` | Личность агента (в каждой сессии) |
| `~/.helix/profiles/<имя>/USER.md` | Факты и предпочтения пользователя |
| `~/.helix/profiles/<имя>/INIT.md` | Маркер онбординга первого запуска |
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