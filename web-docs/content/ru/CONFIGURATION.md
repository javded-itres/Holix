# Конфигурация

## Уровни

1. **Shell** — наивысший приоритет (файлы не перезаписывают экспорт в сессии)
2. **`.env` профиля** — `~/.helix/profiles/<имя>/.env` (только переопределения)
3. **Глобальный `.env`** — `~/.helix/global/.env` (общие ключи API, голос, флаги)
4. **Legacy `.env`** — `~/.helix/.env` (fallback, если нет `global/.env`)
5. **Проектный `.env`** — `./.env` в CWD (удобство для разработки)
6. **YAML профиля** — `~/.helix/profiles/<имя>/config.yaml` (переопределения)
7. **Глобальный YAML** — `~/.helix/global/config.yaml` (общие модели, MCP, поведение)
8. **Флаги CLI** — переопределение на команду

**Наследование:** профили с `--inherit` (по умолчанию) загружают глобальные настройки; значения в файле профиля их перезаписывают. Изменили global — все наследующие профили подхватят при следующем старте (для ключей без override в профиле).

```bash
helix profile global edit              # общие модели, MCP, поведение
helix profile global edit --env        # общий env (Whisper, gateway, …)
helix -p alice profile env --edit      # переопределения только для профиля
helix profile create bob               # наследует global (по умолчанию)
helix profile create carol --clean     # чистый профиль, настройка вручную
```

## Каталог данных (`HELIX_HOME`)

| ОС | По умолчанию |
|----|--------------|
| Linux / macOS | `~/.helix` |
| Windows | `%LOCALAPPDATA%\Helix` |
| Переопределение | `HELIX_HOME` |
| Linux (XDG) | `$XDG_DATA_HOME/helix` без `HELIX_HOME` |

Общее: `global/` (общие настройки), логи, клоны MCP. **На профиль** в `profiles/<имя>/`: `.env`, `config.yaml`, `telegram.env`, `gateway/`, `data/`.

### Глобальные настройки

| Путь | Содержимое |
|------|------------|
| `global/config.yaml` | Общие модели, провайдеры, MCP, search, поведение агента |
| `global/.env` | Общие ключи API, Whisper/голос, gateway, флаги инструментов |

Создаётся при первом запуске (из `profiles/default/config.yaml`, если есть, иначе встроенные дефолты). Управление: `helix profile global show|edit|init`.

### Структура профиля

| Путь | Содержимое |
|------|------------|
| `profiles/<имя>/.env` | Только переопределения (остальное из `global/.env`) |
| `profiles/<имя>/telegram.env` | Токен бота, allowlist, `HELIX_TELEGRAM_USER_PROFILES` |
| `profiles/<имя>/telegram-users.json` | Привязки Telegram user id → профиль Helix |
| `profiles/<имя>/gateway/state.json` | PID и bind запущенного gateway |
| `profiles/<имя>/config.yaml` | Только переопределения (наследует `global/config.yaml`) |
| `profiles/<имя>/data/` | Память, навыки, security, cron |

## Workspace jail (опционально)

Ограничивает файловые и терминальные инструменты одной директорией — удобно, когда на одной машине работают разные люди с разными профилями.

```bash
helix -p data-agent profile jail enable ~/data-agent
helix -p data-agent profile jail status
helix -p data-agent profile jail disable
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
helix -p dev profile whitelist enable
helix -p dev profile whitelist add "ls, cat, python, git"
helix -p dev profile whitelist list
```

Эквивалент в `.env`:

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HELIX_TERMINAL_COMMAND_WHITELIST` | `true` | Проверять whitelist для `run_terminal_command` |
| `HELIX_TERMINAL_WHITELIST_EXTRA` | пусто | Доп. команды или префиксы через запятую |

Встроенные команды платформы всегда разрешены. См. [SECURITY.md](SECURITY.md).

## Telegram (общий бот, много пользователей)

**Рекомендуется** — запросы доступа (`helix telegram setup` включает это по умолчанию):

```bash
helix -p shared telegram requests approve USER_ID --create-profile ivan
```

**Ручные** привязки, когда один бот обслуживает несколько профилей Helix:

```bash
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map import "111:alice,222:bob"
```

| Переменная / файл | Описание |
|-------------------|----------|
| `HELIX_TELEGRAM_ACCESS_REQUESTS` | `true` — пользователи шлют `/start`, админ одобряет из CLI (по умолчанию после `telegram setup`) |
| `HELIX_TELEGRAM_ADMIN_USER_ID` | Единственный Telegram-админ (через `requests approve --set-admin`; только CLI) |
| `HELIX_TELEGRAM_ADMIN_PROFILE` | Профиль Helix администратора (по умолчанию: `admin`) |
| `telegram-access-requests.json` | Ожидающие/обработанные запросы доступа на профиль бота |
| `HELIX_TELEGRAM_ALLOWED_USERS` | Ручной allowlist (не обязателен при access requests) |
| `HELIX_TELEGRAM_USER_PROFILES` | `USER_ID:profile` через запятую в `telegram.env` |
| `telegram-users.json` | Привязки пользователей; обновляется через `map` или `requests approve` |

Подробнее: [TELEGRAM.md](TELEGRAM.md), [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

## Fallback провайдеров (если модель недоступна)

При ошибке основного провайдера (нет соединения, таймаут, rate limit, модель не найдена) Helix пробует **fallback-провайдеры** по порядку.

**На уровне профиля** (в `global/config.yaml` или override в профиле):

```yaml
default_provider: openrouter
fallback_providers:
  - litellm
  - ollama
```

**На уровне провайдера** (до profile-level fallback):

```yaml
providers:
  openrouter:
    fallback_providers: [litellm]
```

CLI:

```bash
helix models fallback list
helix models fallback set litellm,ollama
helix models fallback clear
```

Каждый fallback использует `default_model` своего провайдера. Подробнее: [../en/CONFIGURATION.md](../en/CONFIGURATION.md#provider-fallback-when-llm-is-unavailable).

## Переменные окружения

См. [.env.example](../../.env.example).

### Логирование

`HELIX_LOG_LEVEL`, `HELIX_LOG_DEBUG`, `HELIX_LOG_MAX_BYTES`, `HELIX_LOG_BACKUP_COUNT`, `HELIX_LOG_ROTATION_DAYS` — см. [LOGS.md](LOGS.md) и [../en/CONFIGURATION.md](../en/CONFIGURATION.md#logging).

## Секреты в профиле

```yaml
api_key: ${OPENAI_API_KEY}
providers:
  openai:
    api_key: ${ENV:OPENAI_API_KEY}
```

## Модели

```bash
helix models presets
helix models add openrouter    # OpenAI, DeepSeek, Kimi, Grok, Groq, …
helix models add ollama --host 192.168.1.10:11434
helix models add litellm --host http://proxy.local:4000
helix models add vllm --host gpu-node:8000
helix models setup
helix models list
```

Пресеты: `openai`, `openrouter`, `anthropic` (Claude через OpenRouter), `deepseek`, `moonshot` (Kimi), `xai` (Grok), `groq`, `google`, `mistral`, `ollama`, `litellm`, `vllm`.

**Хост для Ollama / LiteLLM / vLLM:** переменные `OLLAMA_HOST`, `LITELLM_API_BASE`, `VLLM_HOST` в `.env` или флаг `--host` при `helix models add` (также запрос в `models setup`). Порты по умолчанию: 11434, 4000, 8000. Подробнее: [../en/CONFIGURATION.md](../en/CONFIGURATION.md#host-for-ollama-litellm-vllm).

Секреты в YAML: `${OPENAI_API_KEY}`, `${ENV:DEEPSEEK_API_KEY}`. OpenRouter: также `OPENROUTER_HTTP_REFERER` в `.env`.

Подробнее: [../en/CONFIGURATION.md](../en/CONFIGURATION.md#provider-catalog).

Поля `model` / `base_url` в корне YAML поддерживаются; предпочтительны `providers` + `default_provider`.