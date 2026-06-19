# Конфигурация

## Уровни

1. **Shell** — наивысший приоритет (файлы не перезаписывают экспорт в сессии)
2. **`.env` профиля** — `~/.holix/profiles/<имя>/.env` (только переопределения)
3. **Глобальный `.env`** — `~/.holix/global/.env` (общие ключи API, голос, флаги)
4. **Legacy `.env`** — `~/.holix/.env` (fallback, если нет `global/.env`)
5. **Проектный `.env`** — `./.env` в CWD (удобство для разработки)
6. **YAML профиля** — `~/.holix/profiles/<имя>/config.yaml` (переопределения)
7. **Глобальный YAML** — `~/.holix/global/config.yaml` (общие модели, MCP, поведение)
8. **Флаги CLI** — переопределение на команду

**Наследование:** профили с `--inherit` (по умолчанию) загружают глобальные настройки; значения в файле профиля их перезаписывают. Изменили global — все наследующие профили подхватят при следующем старте (для ключей без override в профиле).

```bash
holix profile global edit              # общие модели, MCP, поведение
holix profile global edit --env        # общий env (Whisper, gateway, …)
holix -p alice profile env --edit      # переопределения только для профиля
holix profile create bob               # наследует global (по умолчанию)
holix profile create carol --clean     # чистый профиль, настройка вручную
```

## Каталог данных (`HOLIX_HOME`)

| ОС | По умолчанию |
|----|--------------|
| Linux / macOS | `~/.holix` |
| Windows | `%LOCALAPPDATA%\Holix` |
| Переопределение | `HOLIX_HOME` |
| Linux (XDG) | `$XDG_DATA_HOME/holix` без `HOLIX_HOME` |

Общее: `global/` (общие настройки), логи, клоны MCP. **На профиль** в `profiles/<имя>/`: `.env`, `config.yaml`, `telegram.env`, `gateway/`, `data/`.

### Глобальные настройки

| Путь | Содержимое |
|------|------------|
| `global/config.yaml` | Общие модели, провайдеры, MCP, search, поведение агента |
| `global/.env` | Общие ключи API, Whisper/голос, gateway, флаги инструментов |

Создаётся при первом запуске (из `profiles/default/config.yaml`, если есть, иначе встроенные дефолты). Управление: `holix profile global show|edit|init`.

### Структура профиля

| Путь | Содержимое |
|------|------------|
| `profiles/<имя>/.env` | Только переопределения (остальное из `global/.env`) |
| `profiles/<имя>/telegram.env` | Токен бота, allowlist, `HOLIX_TELEGRAM_USER_PROFILES` |
| `profiles/<имя>/telegram-users.json` | Привязки Telegram user id → профиль Holix |
| `profiles/<имя>/gateway/state.json` | PID и bind запущенного gateway |
| `profiles/<имя>/config.yaml` | Только переопределения (наследует `global/config.yaml`) |
| `profiles/<имя>/SOUL.md` | Личность агента (вставляется в каждую сессию) |
| `profiles/<имя>/USER.md` | Факты и предпочтения пользователя |
| `profiles/<имя>/INIT.md` | Маркер онбординга (удаляется после `complete_agent_initialization`) |
| `profiles/<имя>/data/` | Память, навыки, security, cron |
| `profiles/<имя>/workspace/` | Workspace агента (plaintext, не шифруется) |

### Загрузка `telegram.env`

Holix читает `profiles/<хост-бота>/telegram.env` после bootstrap и unlock профиля. Значения из файла **перезаписывают пустые** записи в shell/global (например, пустой `TELEGRAM_BOT_TOKEN=`). Для зашифрованных файлов нужен `HOLIX_UNLOCK_KEY` в окружении или сессия `holix profile crypto unlock`.

## Шифрование профиля (опционально)

Holix шифрует **секреты профиля на диске**: `.env`, `telegram.env`, `SOUL.md`, `USER.md`, БД памяти. **Файлы workspace остаются plaintext** (удобно для git). Старые зашифрованные workspace мигрируют командой `holix profile crypto decrypt-workspace`.

```bash
holix -p alice profile crypto enable           # один профиль
holix profile crypto migrate --all --yes       # массово на существующих установках
holix -p alice profile crypto unlock         # расшифровка для CLI-сессии
holix profile crypto decrypt-workspace --all --yes   # миграция workspace
holix -p alice profile crypto status
```

| Переменная | Назначение |
|------------|------------|
| `HOLIX_UNLOCK_KEY` | Ключ пользователя для unlock зашифрованных профилей при старте gateway |
| `HOLIX_ENCRYPTION_MODE` | Метка политики (`linux-production` и т.д.) |

Вложения в Telegram перед отправкой материализуются в plaintext при включённом шифровании.

Полный гайд (политика по ОС, модель угроз, unlock gateway): [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md).  
См. также [SECURITY.md](SECURITY.md#шифрование-на-диске) и `holix profile crypto --help`.

## Workspace jail (опционально)

Ограничивает файловые и терминальные инструменты одной директорией — удобно, когда на одной машине работают разные люди с разными профилями.

```bash
holix -p data-agent profile jail enable ~/data-agent
holix -p data-agent profile jail status
holix -p data-agent profile jail disable
```

Или в `config.yaml`:

```yaml
workspace_jail_enabled: true
workspace_root: /home/user/data-agent
```

При включении `read_file`, `write_file`, `list_directory`, `run_terminal_command` и отправка файлов в Telegram не выходят за пределы `workspace_root`.

## Whitelist терминала (опционально)

Ограничение shell-команд агента. Настраивается для каждого профиля:

```bash
holix -p dev profile whitelist enable
holix -p dev profile whitelist add "ls, cat, python, git"
holix -p dev profile whitelist list
```

Эквивалент в `.env`:

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HOLIX_TERMINAL_COMMAND_WHITELIST` | `true` | Проверять whitelist для `run_terminal_command` |
| `HOLIX_TERMINAL_WHITELIST_EXTRA` | пусто | Доп. команды или префиксы через запятую |

Встроенные команды платформы всегда разрешены. См. [SECURITY.md](SECURITY.md).

## Telegram (общий бот, много пользователей)

**Рекомендуется** — запросы доступа (`holix telegram setup` включает это по умолчанию):

```bash
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

**Ручные** привязки, когда один бот обслуживает несколько профилей Holix:

```bash
holix -p shared telegram map set 123456789 alice
holix -p shared telegram map import "111:alice,222:bob"
```

| Переменная / файл | Описание |
|-------------------|----------|
| `HOLIX_TELEGRAM_ACCESS_REQUESTS` | `true` — пользователи шлют `/start`, админ одобряет из CLI (по умолчанию после `telegram setup`) |
| `HOLIX_TELEGRAM_ADMIN_USER_ID` | Единственный Telegram-админ (через `requests approve --set-admin`; только CLI) |
| `HOLIX_TELEGRAM_ADMIN_PROFILE` | Профиль Holix администратора (по умолчанию: `admin`) |
| `telegram-access-requests.json` | Ожидающие/обработанные запросы доступа на профиль бота |
| `HOLIX_TELEGRAM_ALLOWED_USERS` | Ручной allowlist (не обязателен при access requests) |
| `HOLIX_TELEGRAM_USER_PROFILES` | `USER_ID:profile` через запятую в `telegram.env` |
| `telegram-users.json` | Привязки пользователей; обновляется через `map` или `requests approve` |

Подробнее: [TELEGRAM.md](TELEGRAM.md) (в т.ч. несколько профилей)

## Модели

Провайдеры, `agent_models`, fallback — **[MODELS.md](MODELS.md)**.

## MCP и Hub

- MCP — **[MCP.md](MCP.md)** и `holix mcp` в [CLI.md](CLI.md)
- Hub lockfile: `{profile}/data/hub-lock.json` — [HUB.md](HUB.md)
- `skill_assignments` — `holix skills assign`

## Переменные окружения

См. [.env.example](../../.env.example).

### Логирование

`HOLIX_LOG_LEVEL`, `HOLIX_LOG_DEBUG`, `HOLIX_LOG_MAX_BYTES`, `HOLIX_LOG_BACKUP_COUNT`, `HOLIX_LOG_ROTATION_DAYS` — см. [LOGS.md](LOGS.md) и [../en/CONFIGURATION.md](../en/CONFIGURATION.md#logging).

## Секреты в профиле

```yaml
api_key: ${OPENAI_API_KEY}
providers:
  openai:
    api_key: ${ENV:OPENAI_API_KEY}
```

## Генерация плана (режимы Plan и Hybrid)

`.env` профиля / `config.yaml` (см. [EXECUTION_MODES.md](EXECUTION_MODES.md#настройки)):

| Переменная | По умолчанию | Эффект |
|------------|--------------|--------|
| `plan_review_enabled` | `true` | Показывать план на согласование до выполнения |
| `plan_review_timeout` | `600` | Секунд ожидания решения по плану |
| `plan_generation_timeout` | `600` | Секунд ожидания генерации плана LLM |
| `plan_generation_max_tokens` | `12000` | Макс. токенов для JSON плана (большие отчёты) |
| `plan_generation_retries` | `2` | Повторы при таймауте или обрезанном JSON |
| `max_steps_per_plan_step` | `5` | Итераций инструментов на шаг плана |
| `max_steps` | `15` | Общий лимит шагов графа |

## Локальные дополнения проекта

В каталоге проекта Holix может подмешивать (не перезаписывая системные ключи профиля):

- `./.holix/skills/` — дополнительные навыки
- `./.holix/plans/` — согласованные планы (`.md` для чтения, `.json` для машины); устаревший `./.holix/plan/` по-прежнему читается
- `./config.yaml` — доп. MCP/навыки (не полная замена профиля)