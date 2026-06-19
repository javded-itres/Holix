# Модели и провайдеры

Holix направляет запросы к LLM через **провайдеры** в `config.yaml` профиля. Настройка: **`holix models`**.

---

## Быстрый старт

```bash
holix models setup
holix models list
holix models agents
holix models fallback list
```

Мастер проверяет подключение и записывает `default_provider`, `providers`, `agent_models`.

---

## Провайдеры

| Пресет | Назначение |
|--------|------------|
| `openrouter` | Облачные модели |
| `openai` | OpenAI API |
| `groq` | Groq |
| `ollama` | Локальный Ollama (`OLLAMA_HOST`, порт 11434) |
| `litellm` | Прокси LiteLLM (`LITELLM_API_BASE`, порт 4000) |
| `vllm` | vLLM (`VLLM_HOST`, порт 8000) |

Пример:

```yaml
default_provider: litellm
providers:
  litellm:
    base_url: http://127.0.0.1:4000/v1
    api_key: ${LITELLM_API_KEY}
    default_model: smart
  ollama:
    base_url: http://127.0.0.1:11434/v1
    default_model: qwen2.5-coder:32b
```

Подробнее про хосты: [CONFIGURATION.md](CONFIGURATION.md).

---

## Маршрутизация по агентам (`agent_models`)

```yaml
agent_models:
  main:
    provider: litellm
    model: smart
  coder:
    provider: litellm
    model: heavy
```

CLI: `holix models agents`. В чате: `/models` (TUI).

Субагенты по умолчанию используют **модель родителя** — [SUBAGENTS.md](SUBAGENTS.md).

---

## Fallback

При сбое основного провайдера Holix перебирает запасные.

```yaml
fallback_providers:
  - litellm
  - ollama
```

```bash
holix models fallback set litellm,ollama
holix models fallback clear
```

Наследование из `~/.holix/global/config.yaml`.

---

## Global и профиль

| Слой | Путь |
|------|------|
| Global | `~/.holix/global/config.yaml` |
| Профиль | `profiles/<имя>/config.yaml` |
| Секреты | `.env` профиля |

```bash
holix profile global edit
holix config show
```

---

## Gateway

- `GET /v1/models` — [GATEWAY.md](GATEWAY.md)
- `/api/holix/profiles/{id}/models` — [GATEWAY_API.md](GATEWAY_API.md)

---

## Проблемы

```bash
holix doctor --fix
holix models setup
```

---

## См. также

- [CONFIGURATION.md](CONFIGURATION.md)
- [CLI.md](CLI.md)
- [EXECUTION_MODES.md](EXECUTION_MODES.md)