# Справочник CLI

Точка входа: **`holix`** (Typer).

## Глобальные опции

| Опция | Кратко | По умолчанию | Описание |
|-------|--------|--------------|----------|
| `--profile` | `-p` | *(dev: `default`)* | Профиль в `~/.holix/profiles/<имя>/` |
| `--profile-key` | | env `HOLIX_PROFILE_KEY` | Ключ доступа к защищённому профилю |
| `--verbose` | `-v` | выкл | Подробный вывод |

В **development** можно не указывать `-p` — используется `default`. В **production** (`HOLIX_ENV=production`) нужен **именованный** профиль — `default` недоступен:

```bash
holix gateway start
holix -p work status
HOLIX_ENV=production holix -p shared gateway start
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

## `holix chat-command`

```bash
holix chat-command
holix chat-command -m qwen2.5-coder:32b --max-steps 20
```

Опции: `--model`, `--temperature`, `--max-steps`.

Слэши: `/help`, `/exit`, `/clear`, `/model`, `/profile`, `/skills`, `/memory`, `/status`, `/metrics`, `/stream`, `/debug`, `/compress` — см. [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

---

## `holix run`

```bash
holix run "Кратко опиши репозиторий"
holix run "…" -c id_разговора
```

---

## `holix tui`

```bash
holix tui
holix tui --web
holix tui --web --allow-lan --token "$(openssl rand -hex 32)"
```

Legacy: `HOLIX_TUI_LEGACY=1 holix tui`.  
Подробнее: [TUI.md](TUI.md).

---

## `holix status` / `clear` / `version`

- **status** — модель, URL, каталоги, список профилей  
- **clear** — удаление памяти и навыков (`-y` без подтверждения)  
- **version** — версия пакета  

---

## `holix install` / `update`

```bash
holix install
holix install --extra telegram
holix update --check
```

См. [INSTALLATION.md](INSTALLATION.md).

---

## `holix bootstrap`

Первичная настройка после установки: язык (RU/EN), LLM, опционально Telegram. Вызывается автоматически из `install.sh`.

```bash
holix bootstrap
holix bootstrap --lang ru
holix bootstrap --skip-telegram
holix bootstrap -y
```

| Опция | Описание |
|-------|----------|
| `--lang` | Язык мастера (`en` \| `ru`); на русской системе выбор не спрашивается |
| `--skip-llm` | Пропустить настройку LLM |
| `--skip-telegram` | Пропустить Telegram |
| `-y`, `--yes` | Без интерактива |
| `-p`, `--profile` | Профиль Holix (по умолчанию `default`) |

Записывает локаль в `profiles/default/data/locale.json` и `profiles/admin/data/locale.json`. См. [INSTALLATION.md](INSTALLATION.md).

---

## `holix config`

| Подкоманда | Описание |
|------------|----------|
| `show` | YAML профиля |
| `edit` | Редактор `$EDITOR` |
| `set ключ значение` | Поле `ProfileConfig` |

---

## `holix models`

| Подкоманда | Описание |
|------------|----------|
| `setup` | Мастер провайдеров, `agent_models`, fallback |
| `list` | Список провайдеров |
| `agents` | Назначения по агентам |
| `fallback list` | Цепочка fallback-провайдеров |
| `fallback set PROVIDERS` | Задать fallback (`litellm,ollama`) |
| `fallback clear` | Убрать fallback на уровне профиля |

```bash
holix models setup
holix models fallback set litellm,ollama
holix models fallback list
```

---

## `holix skills`

| Подкоманда | Описание |
|------------|----------|
| `list` | Список (`--agent`) |
| `search` | Поиск |
| `show` | Текст навыка |
| `assign` / `unassign` | `skill_assignments` |
| `agents` | Какие агенты видят навык |
| `assign-wizard` | Интерактивное назначение |

---

## `holix memory`

`holix memory search "<запрос>"` — в TUI: `/memory <запрос>`.

---

## `holix profile`

Изоляция профиля и **общие глобальные настройки** (наследуются по умолчанию).

| Подкоманда | Описание |
|------------|----------|
| `create <имя>` | Новый профиль (`--inherit` по умолчанию, `--clean` — без global) |
| `create <имя> --protect` | С ключом доступа + workspace jail |
| `global show` | Показать `~/.holix/global/config.yaml` |
| `global edit` | Редактировать global YAML (модели, MCP, поведение) |
| `global edit --env` | Редактировать `~/.holix/global/.env` |
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
holix profile global edit
holix profile create team-a
holix profile create team-b --clean
holix -p alice profile env --edit
holix -p data-agent profile jail enable ~/data-agent
```

[CONFIGURATION.md](CONFIGURATION.md), [PROFILES.md](PROFILES.md)

---

## `holix gateway`

Привязан к **активному профилю** (`-p`). Несколько gateway на разных портах.

| Подкоманда | Описание |
|------------|----------|
| `start` | Фоновый запуск |
| `stop` | Остановка gateway этого профиля |
| `status` | Статус этого профиля |
| `reload` | Перезапуск |

```bash
holix -p alice gateway start -f
```

Состояние: `profiles/<имя>/gateway/state.json` · [GATEWAY.md](GATEWAY.md)

### Ключи gateway API

**Нет** CLI-команды `holix` для создания ключей gateway (`hx_…`). Варианты:

```bash
# curl (нужен существующий admin hx_ key)
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys?name=my-app&permissions=read,write" \
  -H "Authorization: Bearer hx_admin_…"

# или Swagger UI после holix gateway start
open http://127.0.0.1:8000/docs   # Authorize → HolixApiKey → вставьте hx_…
```

**Ключи доступа к профилю** (`hp_…`) — другое назначение: защита переключения профиля и `/api/holix/*` management, не HTTP-поверхность gateway:

```bash
holix -p alice profile key init    # генерирует hp_… (показывается один раз)
holix -p alice --profile-key hp_…  # использование в CLI/TUI
```

Первый admin-ключ: временно `HOLIX_REQUIRE_AUTH=false`, создайте через `POST /admin/api-keys`, затем включите auth. Полный справочник: [GATEWAY_API.md](GATEWAY_API.md).

---

## `holix docs`

Сайт документации (лендинг + SPA, поиск, EN/RU).

| Подкоманда | Описание |
|------------|----------|
| *(по умолчанию)* | Запуск на `127.0.0.1:8080` |
| `serve` | То же, что по умолчанию |
| `build` | Синхронизация `docs/en` + `docs/ru` → `web-docs/`, пересборка поиска и SEO |

```bash
holix docs build
holix docs --port 8080 --open
holix gateway start --with-docs
```

См. [DEPLOYMENT.md](DEPLOYMENT.md).

---

## `holix cron`

```bash
holix gateway start
holix cron add "every day at 9 :: Проверить логи"
holix cron list
```

В TUI/Telegram: `/cron`, `/cron add …`. Лог запусков: `profiles/<p>/data/cron/runs.log`.

---

## `holix logs`

```bash
holix logs
holix logs -s agent -l error -n 100
holix logs -f
holix logs list
holix logs rotate
holix logs debug on
```

Источники `-s`: `all`, `agent`, `gateway`, `cron`, `subagent`, `system`.  
Опции: `-n`, `-l`, `-g`, `-f`, `--debug`, `-v`. Полная версия: [LOGS.md](LOGS.md).

---

## `holix doctor`

```bash
holix doctor
holix doctor --fix
holix doctor --no-llm
```

[DOCTOR.md](DOCTOR.md)

---

## `holix mcp`

| Подкоманда | Описание |
|------------|----------|
| `list` | Серверы |
| `add` / `remove` | Добавить / удалить |
| `test` | Проверка |
| `assign` / `setup` | Назначение агентам |
| `list-popular` / `install` | Быстрая установка |

Tools: `mcp_<сервер>_<имя>`. В TUI: `/mcp`.

---

## `holix hub`

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

## `holix telegram`

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
| `map set USER_ID PROFILE` | Ручная привязка Telegram user id → профиль Holix |
| `map list` | Список привязок |
| `map remove USER_ID` | Удалить привязку |
| `map bind PROFILE` | Быстрая привязка (`--user-id` или id из allowlist) |
| `map import "ID:prof,..."` | Импорт нескольких привязок |

```bash
holix -p shared telegram setup
holix -p shared telegram requests approve 123456789 --set-admin   # первый админ + профиль admin
holix -p shared telegram requests list
holix -p shared telegram requests approve 123456789 --create-profile ivan
holix -p shared telegram admin show
holix -p shared telegram map set 123456789 alice   # ручная альтернатива
holix -p shared gateway start
```

Один бот на несколько изолированных профилей: [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).  
Общее: [TELEGRAM.md](TELEGRAM.md).

---

## Профили

| Путь | Содержимое |
|------|------------|
| `~/.holix/profiles/<имя>/.env` | Ключи API, порт gateway, флаги |
| `~/.holix/profiles/<имя>/telegram.env` | Токен бота, allowlist, `HOLIX_TELEGRAM_USER_PROFILES` |
| `~/.holix/profiles/<имя>/telegram-users.json` | Привязки Telegram user id → профиль (общий бот) |
| `~/.holix/profiles/<имя>/gateway/` | Состояние и лог gateway |
| `~/.holix/profiles/<имя>/config.yaml` | Модели, MCP, workspace jail |
| `~/.holix/profiles/<имя>/SOUL.md` | Личность агента (в каждой сессии) |
| `~/.holix/profiles/<имя>/USER.md` | Факты и предпочтения пользователя |
| `~/.holix/profiles/<имя>/INIT.md` | Маркер онбординга первого запуска |
| `.../data/memory/` | SQLite + ChromaDB |
| `.../data/skills/` | Навыки |

```bash
holix -p staging tui
holix -p staging profile jail enable ~/staging-workspace
```

---

## См. также

- [SLASH_COMMANDS.md](SLASH_COMMANDS.md)
- [INSTALLATION.md](INSTALLATION.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- [LOGS.md](LOGS.md)
- Полная английская версия: [../en/CLI.md](../en/CLI.md)