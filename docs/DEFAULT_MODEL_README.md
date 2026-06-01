# 🎯 Настройка модели по умолчанию

## Быстрый ответ

**Уже настроено!** ✅

Ваш текущий профиль использует:
- **Провайдер:** litellm
- **URL:** http://192.168.88.252:4000/v1
- **Модель по умолчанию:** fast
- **Доступно моделей:** 111

## Как это работает

### Текущая конфигурация

Файл: `~/.helix/profiles/default/config.yaml`

```yaml
default_provider: litellm  # ← Используется провайдер litellm

providers:
  litellm:
    base_url: http://192.168.88.252:4000/v1
    api_key: sk-1234567890abcdef
    default_model: fast  # ← Модель по умолчанию
    available_models:
      - fast
      - smart
      - heavy
      - research
      - coder
      # ... ещё 106 моделей
```

### Как Helix выбирает модель

```
┌────────────────────────────────────────────────────────┐
│ Helix запускается                                      │
└─────────────────┬──────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────────────────────┐
│ Читает config.yaml                                     │
│ Проверяет: есть ли default_provider?                   │
└─────────────────┬──────────────────────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
    ✅ Да (litellm)    ❌ Нет
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌──────────────────┐
│ Берёт настройки │  │ Использует       │
│ из providers:   │  │ legacy настройки │
│                 │  │ (model, base_url)│
│ base_url        │  └──────────────────┘
│ api_key         │
│ default_model   │
└─────────────────┘
```

## Изменить модель по умолчанию

### Вариант 1: Быстрое изменение

```bash
helix config edit
```

Найдите строку:
```yaml
default_model: fast
```

Измените на любую из доступных:
```yaml
default_model: smart   # Умная модель
# или
default_model: heavy   # Тяжёлая модель
# или
default_model: coder   # Для программирования
```

Сохраните: `Ctrl+O` → `Enter` → `Ctrl+X`

### Вариант 2: Через интерактивный мастер

```bash
helix models setup
```

1. Выберите: `3. Test provider connection`
2. Выберите: `litellm`
3. Helix обновит список моделей
4. Выберите: `2. List providers` (проверить текущие настройки)
5. Для изменения: удалите старый провайдер (`4. Remove provider`)
6. Добавьте заново с нужной моделью (`1. Add new provider`)

### Вариант 3: Программно (Python)

```python
from cli.core import get_profile_manager

manager = get_profile_manager()
config = manager.load_profile("default")

# Изменить модель по умолчанию
config.providers["litellm"]["default_model"] = "smart"

# Сохранить
manager.save_profile("default", config)
```

## Использование разных моделей для разных задач

### Сценарий: Разные модели для разных агентов

```bash
helix models setup
```

Выберите: `5. Configure agent models`

Настройте:
```
Agent: code-reviewer
Provider: litellm
Model: heavy
Temperature: 0.3
→ Точная модель для ревью кода

Agent: quick-search
Provider: litellm
Model: fast
Temperature: 0.8
→ Быстрая модель для поиска

Agent: main
Provider: litellm
Model: smart
Temperature: 0.7
→ Умная модель для основных задач
```

Теперь в config.yaml:
```yaml
agent_models:
  code-reviewer:
    provider: litellm
    model: heavy
    temperature: 0.3

  quick-search:
    provider: litellm
    model: fast
    temperature: 0.8

  main:
    provider: litellm
    model: smart
    temperature: 0.7
```

## Проверка текущих настроек

### Команды для проверки

```bash
# Показать все провайдеры
helix models list

# Показать конфигурацию
helix config show

# Показать назначения моделей агентам
helix models agents

# Статус профиля
helix status
```

### Ожидаемый вывод

```bash
$ helix models list

                    Configured Providers
╭─────────┬─────────────────┬───────────────┬─────────┬─────────╮
│ Name    │ Base URL        │ Default Model │ Models  │ Default │
├─────────┼─────────────────┼───────────────┼─────────┼─────────┤
│ litellm │ http://192...   │ fast          │ 111     │ ✓       │
╰─────────┴─────────────────┴───────────────┴─────────┴─────────╯
```

## Использование в чате

### Запуск с дефолтной моделью

```bash
helix chat-command
```

Вы увидите:
```
Using provider: litellm, model: fast
```

### Переопределение модели для сессии

```bash
# Использовать другую модель
helix chat-command --model smart

# Или в чате
/model heavy
```

### Переопределение температуры

```bash
helix chat-command --temperature 0.3
```

## Множественные провайдеры

Вы можете добавить несколько провайдеров для разных целей:

```yaml
default_provider: litellm  # Основной

providers:
  litellm:
    # Облачные модели для продакшена
    base_url: http://192.168.88.252:4000/v1
    default_model: smart

  ollama:
    # Локальные модели для разработки
    base_url: http://localhost:11434/v1
    default_model: qwen2.5-coder:32b

  openai:
    # Премиум модели для сложных задач
    base_url: https://api.openai.com/v1
    default_model: gpt-4-turbo
```

Затем используйте:
```bash
# Использовать ollama
helix --profile dev chat-command

# В dev профиле настроен default_provider: ollama
```

## Примеры конфигураций

### Минималистичная (один провайдер)

```yaml
default_provider: litellm

providers:
  litellm:
    name: litellm
    base_url: http://192.168.88.252:4000/v1
    api_key: sk-1234567890abcdef
    default_model: smart
    available_models: [fast, smart, heavy, research, coder]
```

### Полная (несколько провайдеров + агенты)

```yaml
default_provider: litellm

providers:
  litellm:
    name: litellm
    base_url: http://192.168.88.252:4000/v1
    api_key: sk-1234567890abcdef
    default_model: smart
    available_models: [fast, smart, heavy, research, coder]

  ollama:
    name: ollama
    base_url: http://localhost:11434/v1
    api_key: ollama
    default_model: qwen2.5-coder:32b
    available_models: [qwen2.5-coder:32b, llama3.2:3b]

agent_models:
  main:
    provider: litellm
    model: smart
    temperature: 0.7

  code-reviewer:
    provider: ollama
    model: qwen2.5-coder:32b
    temperature: 0.3

  researcher:
    provider: litellm
    model: research
    temperature: 0.8
```

## Troubleshooting

### Модель не найдена

**Проблема:** `Model 'xyz' not found`

**Решение:**
```bash
# Проверить доступные модели
helix config show | grep -A 50 "available_models"

# Или обновить список моделей
helix models setup
# Выбрать: 3. Test provider connection
```

### Connection refused

**Проблема:** Не могу подключиться к провайдеру

**Решение:**
```bash
# Проверить доступность
curl http://192.168.88.252:4000/v1/models

# Проверить с API ключом
curl -H "Authorization: Bearer sk-1234567890abcdef" \
  http://192.168.88.252:4000/v1/models
```

### Helix использует старую модель

**Проблема:** После изменения config.yaml модель не обновилась

**Решение:**
```bash
# Перезапустить чат
# Ctrl+C в старой сессии
helix chat-command

# Проверить конфигурацию
helix config show | grep default_model
```

### Хочу вернуться к Ollama

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

Или используйте legacy режим (удалите `default_provider`):
```yaml
model: qwen2.5-coder:32b
base_url: http://localhost:11434/v1
api_key: ollama
temperature: 0.7
```

## Дополнительно

### Документация

- **Полное руководство:** `docs/QUICK_MODEL_SETUP.md`
- **Все модели:** `MODELS_SETUP.md`
- **Changelog:** `CHANGELOG.md`

### Команды для управления

```bash
helix models setup      # Интерактивная настройка
helix models list       # Список провайдеров
helix models agents     # Назначения агентам
helix config show       # Показать конфигурацию
helix config edit       # Редактировать конфигурацию
helix status            # Статус профиля
```

---

**Последнее обновление:** 2025-06-01
**Версия Helix:** 0.1.0
**Ваша конфигурация:** `~/.helix/profiles/default/config.yaml`
