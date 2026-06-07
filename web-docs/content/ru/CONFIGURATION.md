# Конфигурация

## Уровни

1. **`.env`** — глобальные значения (`config.py` / `Settings`), основной файл: **`~/.helix/.env`**
2. **Профиль** — `~/.helix/profiles/<name>/config.yaml`
3. **Флаги CLI** — переопределение на команду

Опционально `./.env` в каталоге проекта (ниже приоритетом, чем `~/.helix/.env`). Переменные shell не перезаписываются.

```bash
cp .env.example ~/.helix/.env
```

## Каталог данных (`HELIX_HOME`)

| ОС | По умолчанию |
|----|--------------|
| Linux / macOS | `~/.helix` |
| Windows | `%LOCALAPPDATA%\Helix` |
| Переопределение | `HELIX_HOME` |
| Linux (XDG) | `$XDG_DATA_HOME/helix` без `HELIX_HOME` |

Профили, логи, gateway и MCP-клоны — в этом каталоге.

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