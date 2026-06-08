# Конфигурация

## Уровни

1. **Shell** — наивысший приоритет (файлы не перезаписывают экспорт в сессии)
2. **`.env` профиля** — `~/.helix/profiles/<имя>/.env` (ключи API, порт gateway, флаги)
3. **Глобальный `.env`** — `~/.helix/.env` (legacy, для старых установок)
4. **Проектный `.env`** — `./.env` в CWD (удобство для разработки)
5. **YAML профиля** — `~/.helix/profiles/<имя>/config.yaml` (модели, MCP, навыки)
6. **Флаги CLI** — переопределение на команду

Каждый профиль изолирован: свой env, Telegram, состояние gateway, память и навыки.

```bash
helix -p alice profile env --edit
cp .env.example ~/.helix/profiles/default/.env
```

## Каталог данных (`HELIX_HOME`)

| ОС | По умолчанию |
|----|--------------|
| Linux / macOS | `~/.helix` |
| Windows | `%LOCALAPPDATA%\Helix` |
| Переопределение | `HELIX_HOME` |
| Linux (XDG) | `$XDG_DATA_HOME/helix` без `HELIX_HOME` |

Общее: логи, клоны MCP. **На профиль** в `profiles/<имя>/`: `.env`, `config.yaml`, `telegram.env`, `gateway/`, `data/`.

### Структура профиля

| Путь | Содержимое |
|------|------------|
| `profiles/<имя>/.env` | Ключи API, `HELIX_GATEWAY_PORT`, флаги инструментов |
| `profiles/<имя>/telegram.env` | Токен бота и allowlist |
| `profiles/<имя>/gateway/state.json` | PID и bind запущенного gateway |
| `profiles/<имя>/config.yaml` | Модели, MCP, hub, workspace jail |
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