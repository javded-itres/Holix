# 🚀 Быстрая настройка модели по умолчанию

## Способ 1: Через интерактивный мастер (рекомендуется)

### Шаг 1: Запустите настройку

```bash
helix models setup
```

### Шаг 2: Добавьте провайдер

Выберите `1. Add new provider`

```
Provider name: litellm
Base URL: http://192.168.88.252:4000/v1
API key: sk-1234567890abcdef
```

Helix автоматически:
- Проверит подключение ✅
- Обнаружит все доступные модели 🔍
- Покажет их в таблице 📋
- Установит провайдер как дефолтный (если это первый провайдер) ⭐

### Шаг 3: Выберите модель по умолчанию

Helix предложит выбрать модель из списка обнаруженных моделей.

Например:
```
Default model to use: smart
```

### Шаг 4: Сохраните

Выберите `7. Save and exit`

Готово! ✨

## Способ 2: Редактирование конфигурации вручную

### Откройте конфигурацию

```bash
helix config edit
# или
nano ~/.helix/profiles/default/config.yaml
```

### Добавьте провайдер

```yaml
# Установить провайдер по умолчанию
default_provider: litellm

# Добавить провайдеры
providers:
  litellm:
    name: litellm
    base_url: http://192.168.88.252:4000/v1
    api_key: sk-1234567890abcdef
    default_model: smart  # ← Ваша модель по умолчанию
    available_models:
      - fast
      - smart
      - heavy
      - research
      - coder
      # ... остальные модели
```

### Сохраните и закройте

Нажмите `Ctrl+O`, затем `Enter`, затем `Ctrl+X`

## Проверка настроек

### Посмотреть текущую конфигурацию

```bash
helix config show
```

Вы должны увидеть:
```yaml
default_provider: litellm
providers:
  litellm:
    base_url: http://192.168.88.252:4000/v1
    default_model: smart
```

### Посмотреть список провайдеров

```bash
helix models list
```

Вывод:
```
╭───────────────── Configured Providers ─────────────────╮
│ Name    │ Base URL            │ Default Model │ Default │
├─────────┼─────────────────────┼───────────────┼─────────┤
│ litellm │ http://192.168...   │ smart         │ ✓       │
╰─────────────────────────────────────────────────────────╯
```

## Использование

### В чате

```bash
helix chat-command
```

При инициализации вы увидите:
```
Using provider: litellm, model: smart
```

Теперь все запросы будут использовать модель `smart` через провайдер `litellm`! 🎉

### В разовых запросах

```bash
helix run "What is the capital of France?"
```

Будет использоваться модель `smart` от провайдера `litellm`.

### Переопределить модель для конкретного запроса

```bash
# Использовать другую модель из провайдера
helix chat-command --model heavy

# В чате через команду
/model research
```

## Настройка моделей для разных агентов

Если вы хотите использовать разные модели для разных задач:

```bash
helix models setup
# Выберите: 5. Configure agent models
```

Пример:
```
Agent name: code-reviewer
Provider: litellm
Model: heavy
Temperature: 0.3

Agent name: quick-search
Provider: litellm
Model: fast
Temperature: 0.8
```

Теперь:
- Агент `code-reviewer` будет использовать `heavy` (точная модель)
- Агент `quick-search` будет использовать `fast` (быстрая модель)
- Все остальные будут использовать дефолтную модель `smart`

## Множественные провайдеры

Вы можете добавить несколько провайдеров:

```bash
helix models setup
```

Добавьте:
1. **litellm** - для облачных моделей
2. **ollama** - для локальных моделей
3. **openai** - для официальных OpenAI моделей

```yaml
default_provider: litellm  # Основной провайдер

providers:
  litellm:
    default_model: smart

  ollama:
    base_url: http://localhost:11434/v1
    default_model: qwen2.5-coder:32b

  openai:
    base_url: https://api.openai.com/v1
    default_model: gpt-4-turbo
```

Затем назначьте агентам:
```yaml
agent_models:
  main:
    provider: litellm    # Быстрый облачный
    model: smart

  code-generator:
    provider: ollama     # Локальный для приватности
    model: qwen2.5-coder:32b

  expert-review:
    provider: openai     # Премиум для сложных задач
    model: gpt-4-turbo
```

## Проверка работы

### Тест в консоли

```bash
echo "Testing default model..."
helix run "Say hello in one word"
```

Должно использоваться: `litellm` → `smart`

### Посмотреть активные настройки

```bash
helix status
```

## Troubleshooting

### Модель не работает / Connection refused

1. Проверьте доступность провайдера:
```bash
curl http://192.168.88.252:4000/v1/models
```

2. Проверьте API ключ:
```bash
curl -H "Authorization: Bearer sk-1234567890abcdef" \
  http://192.168.88.252:4000/v1/models
```

3. Протестируйте провайдер:
```bash
helix models setup
# Выберите: 3. Test provider connection
```

### Helix использует старую модель

1. Проверьте `default_provider`:
```bash
helix config show | grep default_provider
```

2. Убедитесь что провайдер добавлен:
```bash
helix models list
```

3. Пересоздайте профиль:
```bash
helix --profile test models setup
helix --profile test chat-command
```

### Как вернуться к локальному Ollama

```bash
helix config edit
```

Измените:
```yaml
default_provider: ollama

providers:
  ollama:
    name: ollama
    base_url: http://localhost:11434/v1
    api_key: ollama
    default_model: qwen2.5-coder:32b
```

Или удалите блок `providers` и используйте legacy режим:
```yaml
model: qwen2.5-coder:32b
base_url: http://localhost:11434/v1
api_key: ollama
```

---

**Обновлено:** 2025-06-01
**Версия:** Helix 0.1.0
