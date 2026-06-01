# 🎯 Настройка моделей в Helix

Helix поддерживает подключение множественных провайдеров моделей (Ollama, LiteLLM, OpenAI и любые OpenAI-совместимые API) и позволяет назначать разные модели для разных агентов и субагентов.

## Быстрый старт

### 1. Запустите интерактивную настройку

```bash
helix models setup
```

Это откроет интерактивный мастер настройки с меню:

```
🔧 Model Provider Setup

Configure OpenAI-compatible model providers (Ollama, LiteLLM, OpenAI, etc.)
and assign models to agents and sub-agents.

Available actions:
1. Add new provider
2. List providers
3. Test provider connection
4. Remove provider
5. Configure agent models
6. View agent model assignments
7. Save and exit
8. Exit without saving
```

### 2. Добавьте провайдер (например, LiteLLM)

Выберите `1` → Введите данные:

```
Provider name: litellm
Base URL: http://localhost:4000/v1
API key: sk-1234567890
```

Helix автоматически:
- Проверит подключение
- Обнаружит доступные модели
- Отобразит их в таблице
- Предложит выбрать модель по умолчанию

### 3. Настройте модели для агентов

Выберите `5` → Введите:

```
Agent/Sub-agent name: code-reviewer
Provider: litellm
Model: gpt-4o-mini
Temperature: 0.7
```

Теперь когда вы создадите агента с именем `code-reviewer`, он будет использовать `gpt-4o-mini` через LiteLLM.

## Примеры конфигурации

### Ollama (локальный)

```
Provider name: ollama
Base URL: http://localhost:11434/v1
API key: ollama
Default model: qwen2.5-coder:32b
```

### LiteLLM (множественные провайдеры)

```
Provider name: litellm
Base URL: http://localhost:4000/v1
API key: sk-your-key-here
Default model: gpt-4o-mini
```

### OpenAI (официальный API)

```
Provider name: openai
Base URL: https://api.openai.com/v1
API key: sk-your-openai-key
Default model: gpt-4-turbo
```

### Groq (быстрый inference)

```
Provider name: groq
Base URL: https://api.groq.com/openai/v1
API key: gsk-your-groq-key
Default model: llama-3.1-70b-versatile
```

## Конфигурация агентов

### Основной агент

```bash
# В интерактивной настройке
Agent name: main
Provider: ollama
Model: qwen2.5-coder:32b
Temperature: 0.7
```

### Субагенты для разных задач

```bash
# Агент для ревью кода (нужна точность)
Agent name: code-reviewer
Provider: openai
Model: gpt-4-turbo
Temperature: 0.3

# Агент для исследований (нужна скорость)
Agent name: research
Provider: groq
Model: llama-3.1-8b-instant
Temperature: 0.8

# Агент для генерации тестов
Agent name: test-generator
Provider: litellm
Model: claude-3-5-sonnet
Temperature: 0.5
```

## Структура конфигурации

После настройки в `~/.helix/profiles/default/config.yaml`:

```yaml
# Провайдеры
providers:
  ollama:
    name: ollama
    base_url: http://localhost:11434/v1
    api_key: ollama
    default_model: qwen2.5-coder:32b
    available_models:
      - qwen2.5-coder:32b
      - llama3.2:3b
      - codellama:13b

  litellm:
    name: litellm
    base_url: http://localhost:4000/v1
    api_key: sk-1234
    default_model: gpt-4o-mini
    available_models:
      - gpt-4o-mini
      - gpt-4-turbo
      - claude-3-5-sonnet

# Провайдер по умолчанию
default_provider: ollama

# Модели для агентов
agent_models:
  main:
    agent_name: main
    provider: ollama
    model: qwen2.5-coder:32b
    temperature: 0.7

  code-reviewer:
    agent_name: code-reviewer
    provider: litellm
    model: gpt-4-turbo
    temperature: 0.3

  research:
    agent_name: research
    provider: litellm
    model: gpt-4o-mini
    temperature: 0.8
```

## CLI команды

### Список провайдеров

```bash
helix models list
```

Вывод:
```
╭─────────────────────── Configured Providers ───────────────────────╮
│ Name     │ Base URL                  │ Default Model        │ Default │
├──────────┼───────────────────────────┼──────────────────────┼─────────┤
│ ollama   │ http://localhost:11434/v1 │ qwen2.5-coder:32b   │ ✓       │
│ litellm  │ http://localhost:4000/v1  │ gpt-4o-mini         │         │
╰────────────────────────────────────────────────────────────────────╯
```

### Список агентов и их моделей

```bash
helix models agents
```

Вывод:
```
╭─────────────────── Agent Model Assignments ───────────────────╮
│ Agent/Sub-agent  │ Provider │ Model              │ Temp │
├──────────────────┼──────────┼────────────────────┼──────┤
│ main             │ ollama   │ qwen2.5-coder:32b │ 0.7  │
│ code-reviewer    │ litellm  │ gpt-4-turbo       │ 0.3  │
│ research         │ litellm  │ gpt-4o-mini       │ 0.8  │
╰────────────────────────────────────────────────────────────────╯
```

### Интерактивная настройка

```bash
helix models setup
```

## Использование в коде

### Получить модель для агента

```python
from cli.core import get_current_config

config = get_current_config()

# Получить конфигурацию модели для агента
agent_config = config.agent_models.get("code-reviewer")

if agent_config:
    provider_name = agent_config["provider"]
    model_name = agent_config["model"]
    temperature = agent_config["temperature"]

    # Получить провайдер
    provider_data = config.providers[provider_name]
    base_url = provider_data["base_url"]
    api_key = provider_data["api_key"]

    # Создать клиента
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
    )
```

### Создать провайдера программно

```python
from core.models import ModelProvider, ProviderConfig

config = ProviderConfig(
    name="my-litellm",
    base_url="http://localhost:4000/v1",
    api_key="sk-test",
    default_model="gpt-4o-mini"
)

provider = ModelProvider(config)

# Проверить подключение
is_connected = await provider.test_connection()

# Получить модели
models = await provider.get_available_models()
```

### Использовать ModelSelector

```python
from core.models import ModelSelector, AgentModelConfig

selector = ModelSelector()

# Установить модель по умолчанию
default_config = AgentModelConfig(
    agent_name="default",
    provider="ollama",
    model="qwen2.5-coder:32b",
    temperature=0.7
)
selector.set_default_model(default_config)

# Установить модель для специфичного агента
reviewer_config = AgentModelConfig(
    agent_name="code-reviewer",
    provider="openai",
    model="gpt-4-turbo",
    temperature=0.3
)
selector.set_agent_model("code-reviewer", reviewer_config)

# Получить модель для агента
config = selector.get_agent_model("code-reviewer")
```

## Профили и модели

Разные профили могут иметь разные конфигурации моделей:

```bash
# Рабочий профиль с OpenAI
helix --profile work models setup
# Настроить OpenAI провайдер

# Личный профиль с Ollama
helix --profile personal models setup
# Настроить Ollama провайдер

# Экспериментальный профиль с LiteLLM
helix --profile experiments models setup
# Настроить LiteLLM с множеством моделей
```

## Автообнаружение моделей

Helix автоматически обнаруживает модели при добавлении провайдера:

- **Ollama**: `/api/tags` endpoint
- **LiteLLM**: `/v1/models` endpoint
- **OpenAI**: `/v1/models` endpoint

Обнаруженные модели сохраняются в конфигурации и доступны для выбора.

## Тестирование подключения

```bash
helix models setup
# Выбрать: 3. Test provider connection
# Выбрать провайдер для проверки
```

Helix проверит:
- Доступность endpoint
- Корректность API ключа
- Список доступных моделей
- Обновит конфигурацию

## Best Practices

### 1. Разделяйте задачи по моделям

- **Точные задачи** (code review, анализ безопасности): GPT-4, Claude 3.5 Sonnet
- **Быстрые задачи** (поиск, суммаризация): GPT-4o-mini, Llama 3.1 8B
- **Генерация кода**: Qwen 2.5 Coder, CodeLlama
- **Исследования**: Mixtral, Llama 3.1 70B

### 2. Используйте LiteLLM для гибкости

LiteLLM позволяет:
- Объединять множество провайдеров
- Fallback между моделями
- Rate limiting и кеширование
- Единый интерфейс для всех моделей

### 3. Настройте температуру по задачам

- **0.1-0.3**: Детерминированные задачи (code review, тесты)
- **0.5-0.7**: Стандартные задачи (генерация кода, документация)
- **0.8-1.0**: Креативные задачи (brainstorming, дизайн)

### 4. Используйте профили

```bash
# Продакшен - только надежные модели
helix -p production models setup

# Разработка - экспериментальные модели
helix -p dev models setup

# Тестирование - быстрые дешевые модели
helix -p testing models setup
```

## Troubleshooting

### Не могу подключиться к провайдеру

```bash
# Проверьте доступность
curl http://localhost:4000/v1/models

# Проверьте API ключ
curl -H "Authorization: Bearer sk-your-key" \
  http://localhost:4000/v1/models
```

### Модели не обнаруживаются

1. Убедитесь что провайдер запущен
2. Проверьте правильность base_url
3. Проверьте API ключ
4. Попробуйте добавить модели вручную в `config.yaml`

### Агент использует не ту модель

1. Проверьте конфигурацию: `helix models agents`
2. Убедитесь что имя агента совпадает
3. Проверьте что провайдер доступен
4. Fallback на default_provider если агента нет в конфигурации

## Примеры сценариев

### Multi-Model Code Review System

```yaml
agent_models:
  main:
    provider: ollama
    model: qwen2.5-coder:32b
    temperature: 0.7

  security-scanner:
    provider: openai
    model: gpt-4-turbo
    temperature: 0.2

  style-checker:
    provider: litellm
    model: gpt-4o-mini
    temperature: 0.3

  test-generator:
    provider: ollama
    model: codellama:13b
    temperature: 0.5
```

### Multi-Provider Research System

```yaml
agent_models:
  main:
    provider: litellm
    model: gpt-4o-mini
    temperature: 0.7

  deep-analysis:
    provider: openai
    model: gpt-4-turbo
    temperature: 0.5

  fast-search:
    provider: groq
    model: llama-3.1-8b-instant
    temperature: 0.8

  summarizer:
    provider: litellm
    model: claude-3-haiku
    temperature: 0.6
```

### Hybrid Local/Cloud System

```yaml
agent_models:
  main:
    provider: ollama  # Локально
    model: qwen2.5-coder:32b
    temperature: 0.7

  expert-review:
    provider: openai  # Облако для сложных задач
    model: gpt-4-turbo
    temperature: 0.3

  fast-tasks:
    provider: ollama  # Локально для скорости
    model: llama3.2:3b
    temperature: 0.8
```

---

**Документация обновлена:** 2025-06-01
**Версия Helix:** 0.1.0
