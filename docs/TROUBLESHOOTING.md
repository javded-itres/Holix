# 🔧 Troubleshooting Helix

## Tool Calling Errors

### Error: "Tool message must have either name or tool_call_id"

**Полная ошибка:**
```
Error code: 400 - Tool message must have either name or tool_call_id
OpenrouterException - Google
```

**Причина:**
Модель не поддерживает стандартный формат tool calling от OpenAI (обычно это Google/Gemini модели через OpenRouter).

**Решение:**

1. **Быстрое исправление - изменить модель:**

```bash
helix config edit
```

Измените `default_model` на совместимую:
```yaml
providers:
  litellm:
    default_model: smart  # или coder, или claude-sonnet-4-6
```

2. **Проверить какие модели поддерживают tool calling:**

```python
# test_tools.py
import asyncio
from openai import AsyncOpenAI

async def test_model(model_name):
    client = AsyncOpenAI(
        base_url="http://192.168.88.252:4000/v1",
        api_key="sk-1234567890abcdef"
    )

    try:
        await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}]
        )
        print(f"✅ {model_name}")
    except Exception as e:
        print(f"❌ {model_name}: {str(e)[:80]}")

asyncio.run(test_model("smart"))
```

3. **Рекомендуемые модели для Helix:**

- ✅ `smart` - быстрая, работает с tools
- ✅ `coder` - для программирования
- ✅ `heavy` - для сложных задач
- ✅ `claude-sonnet-4-6` - премиум качество
- ✅ `openrouter/anthropic/*` - Claude модели
- ✅ `openrouter/openai/*` - GPT модели
- ❌ `fast` - может не работать (Google/Gemini)

**Проверка:**
```bash
helix models list
# Убедитесь что Default Model = smart (или другая совместимая)
```

---

## Connection Errors

### Error: "Connection refused"

**Причина:** LiteLLM сервер недоступен

**Решение:**
```bash
# Проверить доступность
curl http://192.168.88.252:4000/v1/models

# Если не работает - проверить сервер
ping 192.168.88.252

# Изменить на локальный Ollama
helix config edit
```

```yaml
default_provider: ollama

providers:
  ollama:
    base_url: http://localhost:11434/v1
    api_key: ollama
    default_model: qwen2.5-coder:32b
```

---

## Model Timeout

### Error: Команда висит долго без ответа

**Причина:** Модель медленная или перегружена

**Решение:**

1. **Переключиться на более быструю модель:**
```bash
helix config edit
```

```yaml
default_model: fast  # Быстрая модель
# или
default_model: smart  # Баланс скорость/качество
```

2. **Проверить статус моделей:**
```bash
curl http://192.168.88.252:4000/health
```

3. **Использовать локальный Ollama:**
```bash
# Запустить Ollama
ollama serve

# Переключить на Ollama
helix config edit
```

---

## Invalid API Key

### Error: "401 Unauthorized" или "Invalid API key"

**Решение:**
```bash
helix config edit
```

Проверьте `api_key`:
```yaml
providers:
  litellm:
    api_key: sk-1234567890abcdef  # Правильный ключ
```

Или протестируйте вручную:
```bash
curl -H "Authorization: Bearer sk-1234567890abcdef" \
  http://192.168.88.252:4000/v1/models
```

---

## Model Not Found

### Error: "Model 'xyz' not found"

**Решение:**

1. **Обновить список моделей:**
```bash
helix models setup
# Выбрать: 3. Test provider connection
# Выбрать провайдер
```

2. **Проверить доступные модели:**
```bash
helix config show | grep -A 20 "available_models"
```

3. **Использовать существующую модель:**
```bash
curl http://192.168.88.252:4000/v1/models | jq '.data[].id'
```

---

## Profile Issues

### Не может найти config.yaml

**Решение:**
```bash
# Создать профиль
helix --profile default status

# Или восстановить
mkdir -p ~/.helix/profiles/default
helix config edit
```

### Профиль использует старые настройки

**Решение:**
```bash
# Очистить кеш
rm -rf ~/.helix/profiles/default/data/memory/vector_db

# Пересоздать профиль
helix --profile default-new models setup
```

---

## Memory/Skills Issues

### ChromaDB errors

**Решение:**
```bash
# Очистить векторную БД
rm -rf ~/.helix/profiles/default/data/memory/vector_db

# Очистить навыки
rm -rf ~/.helix/profiles/default/data/skills/*

# Перезапустить
helix chat-command
```

---

## Import Errors

### ModuleNotFoundError: No module named 'core'

**Решение:**
```bash
# Установить пакет
uv sync

# Переустановить в editable mode
uv pip install -e .

# Проверить установку
uv run helix --help
```

---

## CLI Commands Not Working

### Command 'helix' not found

**Решение:**
```bash
# Через uv run
uv run helix --help

# Или установить в PATH
uv pip install -e .

# Проверить установку
which helix
```

### helix models setup - ошибка Progress.update()

**Решение:** Уже исправлено в последней версии.

Если ошибка осталась:
```bash
# Обновить код
git pull

# Переустановить
uv sync
```

---

## Debugging Tips

### Включить verbose режим

```bash
helix --verbose chat-command
```

### Посмотреть логи

```bash
cat ~/.helix/logs/history_default.txt
```

### Проверить конфигурацию

```bash
helix status
helix config show
helix models list
helix models agents
```

### Тестовый запрос

```bash
helix run "test"
```

### Полная диагностика

```bash
echo "=== Helix Status ==="
helix status

echo -e "\n=== Providers ==="
helix models list

echo -e "\n=== Config ==="
helix config show | head -30

echo -e "\n=== Test LiteLLM ==="
curl -s http://192.168.88.252:4000/v1/models | jq '.data[0]'

echo -e "\n=== Test Local Ollama ==="
curl -s http://localhost:11434/api/tags | jq '.models[0]'
```

---

## Получить помощь

1. **Документация:**
   - `MODELS_SETUP.md` - настройка моделей
   - `QUICK_MODEL_SETUP.md` - быстрая настройка
   - `TOOLCALLING_FIX.md` - исправление tool calling

2. **GitHub Issues:**
   - https://github.com/anthropics/helix/issues

3. **Сообщить об ошибке:**
```bash
helix --version
uv run helix run "test" 2>&1 | tee error.log
# Приложить error.log к issue
```

---

**Обновлено:** 2025-06-01
**Версия:** Helix 0.1.0
