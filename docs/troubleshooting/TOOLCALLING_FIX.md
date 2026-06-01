# 🔧 Исправление ошибки Tool Calling

## Проблема

```
Error code: 400 - Tool message must have either name or tool_call_id
```

Это означает, что модель `fast` использует Google/Gemini через OpenRouter, которые не полностью поддерживают стандартный формат tool calling от OpenAI.

## Решение 1: Использовать модель с поддержкой tool calling

### Рекомендуемые модели с поддержкой tool calling:

**Через LiteLLM/OpenRouter:**
- ✅ `claude-opus-4-7` - Anthropic Claude (отличная поддержка)
- ✅ `claude-sonnet-4-6` - Anthropic Claude (отличная поддержка)
- ✅ `gpt-4o` - OpenAI (нативная поддержка)
- ✅ `gpt-4-turbo` - OpenAI (нативная поддержка)
- ✅ `deepseek-chat` - DeepSeek (хорошая поддержка)
- ✅ `qwen-2.5-coder-32b-instruct` - Qwen (поддержка tool calling)

**НЕ рекомендуется (могут не работать с tools):**
- ❌ Модели через Google AI Studio / Gemini
- ❌ Некоторые мелкие модели

### Как изменить модель:

```bash
helix config edit
```

Измените:
```yaml
providers:
  litellm:
    default_model: claude-sonnet-4-6  # было: fast
```

Или используйте:
```bash
helix models setup
```

1. Удалите старый провайдер (4. Remove provider → litellm)
2. Добавьте заново (1. Add new provider)
3. При выборе default_model выберите `claude-sonnet-4-6` или другую из списка выше

## Решение 2: Отключить tool calling (упрощённый режим)

Если хотите использовать модель `fast` без tool calling:

### Создайте профиль без инструментов

```bash
# Создайте новый профиль для simple режима
helix --profile simple config edit
```

Добавьте:
```yaml
model: fast
base_url: http://192.168.88.252:4000/v1
api_key: sk-1234567890abcdef
temperature: 0.7
max_steps: 5  # Меньше шагов, т.к. нет tools

# НЕ добавляйте providers для simple режима
# Helix будет работать в legacy режиме без tool calling
```

Используйте:
```bash
helix --profile simple chat-command
```

### Или модифицируйте агента (временно)

Отключите tools в `core/loop.py`:

```python
# Было:
response = await self.client.chat.completions.create(
    model=self.model,
    messages=api_messages,
    tools=self.agent.tools.get_schemas(),  # ← Закомментировать
    tool_choice="auto",                     # ← Закомментировать
    temperature=settings.temperature
)

# Стало:
response = await self.client.chat.completions.create(
    model=self.model,
    messages=api_messages,
    # tools=self.agent.tools.get_schemas(),  # Отключено
    # tool_choice="auto",                      # Отключено
    temperature=settings.temperature
)
```

⚠️ **Важно:** Без tools агент не сможет читать файлы, выполнять команды и т.д.

## Решение 3: Использовать alias для совместимой модели

Проверьте какая модель стоит за alias `fast`:

```bash
curl -H "Authorization: Bearer sk-1234567890abcdef" \
  http://192.168.88.252:4000/v1/models | grep -A 5 "fast"
```

Если `fast` = Gemini/Google, попросите администратора LiteLLM изменить роутинг на Claude/GPT.

## Решение 4: Прямое использование конкретной модели

Вместо alias используйте полное имя модели:

```bash
helix config edit
```

Измените:
```yaml
providers:
  litellm:
    default_model: openrouter/anthropic/claude-sonnet-4.6
    # Вместо: fast
```

Или в чате:
```bash
helix chat-command --model openrouter/anthropic/claude-sonnet-4.6
```

## Проверка поддержки tool calling

Создайте тестовый скрипт:

```python
#!/usr/bin/env python3
import asyncio
from openai import AsyncOpenAI

async def test_tools():
    client = AsyncOpenAI(
        base_url="http://192.168.88.252:4000/v1",
        api_key="sk-1234567890abcdef"
    )

    tools = [{
        "type": "function",
        "function": {
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }]

    models_to_test = ["fast", "smart", "heavy", "claude-sonnet-4-6"]

    for model in models_to_test:
        print(f"\nTesting {model}...")
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                tools=tools,
                tool_choice="auto"
            )
            print(f"✅ {model} supports tool calling")
        except Exception as e:
            print(f"❌ {model} failed: {str(e)[:100]}")

asyncio.run(test_tools())
```

Запустите:
```bash
python test_tool_support.py
```

## Рекомендация

**Лучший вариант для продакшена:**

1. Используйте модели с нативной поддержкой tool calling:
   - `claude-sonnet-4-6` - баланс цена/качество
   - `gpt-4o` - если нужна OpenAI
   - `deepseek-chat` - если нужна дешёвая альтернатива

2. Настройте:
```bash
helix config edit
```

```yaml
default_provider: litellm

providers:
  litellm:
    base_url: http://192.168.88.252:4000/v1
    api_key: sk-1234567890abcdef
    default_model: claude-sonnet-4-6  # ← Изменить здесь
    available_models:
      - claude-sonnet-4-6
      - claude-opus-4-7
      - gpt-4o
      - deepseek-chat
```

3. Протестируйте:
```bash
helix run "What is 2+2?"
```

Должно работать без ошибок! ✨

## Почему это происходит?

OpenRouter/LiteLLM маршрутизирует запросы к разным провайдерам:
- **Google/Gemini** → Не полностью совместимы с OpenAI tool calling format
- **Claude/GPT** → Полностью совместимы

Когда alias `fast` указывает на Google модель, возникает несовместимость.

**Решение:** Используйте Claude или GPT модели через OpenRouter.

---

**Дата:** 2025-06-01
**Helix версия:** 0.1.0
