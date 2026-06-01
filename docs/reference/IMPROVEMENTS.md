# Helix - Улучшения и новые функции

Этот документ описывает все улучшения, добавленные в Helix агент.

## 🚀 Новые инструменты

### 1. **Поиск в интернете**
```python
# web_search - поиск через DuckDuckGo
Используй web_search для поиска информации в интернете

# fetch_url - загрузка содержимого URL
Используй fetch_url для чтения веб-страниц и API
```

**Примеры:**
```bash
python cli.py "Найди последнюю версию FastAPI"
python cli.py "Загрузи содержимое https://api.github.com/repos/python/cpython"
```

### 2. **Работа с базами данных**
```python
# sql_query - выполнение SQL запросов
# sql_schema - просмотр схемы БД
```

**Примеры:**
```bash
python cli.py "Покажи все таблицы в data/memory/memory.db"
python cli.py "SELECT * FROM conversations LIMIT 5"
```

### 3. **Безопасный запуск Python кода**
```python
# execute_python - запуск Python в sandbox
# calculate - математические вычисления
```

**Примеры:**
```bash
python cli.py "Вычисли факториал 10"
python cli.py "Выполни: print([x**2 for x in range(10)])"
```

---

## 🧠 Улучшенный поиск навыков

Теперь использует **ChromaDB** для семантического поиска:
- Автоматическая индексация навыков при загрузке
- Поиск по смыслу, а не по ключевым словам
- Учёт успешности навыков (success_count / failure_count)

```python
# Навыки автоматически находятся по смыслу запроса
"Создай REST API" → находит skill "create_fastapi_endpoint"
"Работа с БД" → находит skills связанные с базами данных
```

---

## 🔐 Аутентификация и API ключи

### Включение аутентификации

В `api/gateway.py` измени:
```python
REQUIRE_AUTH = True  # Включить аутентификацию
```

### Создание API ключа

```bash
curl -X POST http://localhost:8000/admin/api-keys \
  -d "name=my_app&permissions=read,write&rate_limit=100"
```

Ответ:
```json
{
  "api_key": "hx_xxxxxxxxxxxxxxxxxxxxxx",
  "name": "my_app",
  "permissions": "read,write",
  "rate_limit": 100,
  "warning": "Save this API key securely. It will not be shown again!"
}
```

### Использование API ключа

**Через заголовок Authorization:**
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer hx_xxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

**Через заголовок X-API-Key:**
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "X-API-Key: hx_xxxxxxxxxxxxxx" \
  -d '...'
```

### Управление ключами

**Список ключей:**
```bash
curl http://localhost:8000/admin/api-keys \
  -H "Authorization: Bearer hx_admin_key"
```

**Отзыв ключа:**
```bash
curl -X DELETE http://localhost:8000/admin/api-keys/key_to_revoke \
  -H "Authorization: Bearer hx_admin_key"
```

### Права доступа

- `read` - чтение (chat, conversations, skills)
- `write` - запись (требуется для tool вызовов)
- `execute` - выполнение команд
- `admin` - все права + управление ключами

---

## 🌊 Streaming (потоковая передача)

Получай ответы в реальном времени:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "helix",
    "messages": [{"role": "user", "content": "Расскажи длинную историю"}],
    "stream": true
  }'
```

Ответ (Server-Sent Events):
```
data: {"type": "content", "content": "Однажды"}
data: {"type": "content", "content": " в"}
data: {"type": "content", "content": " далёкой"}
data: {"type": "tool_call", "tool": "web_search"}
data: {"type": "tool_result", "tool": "web_search", "result": "..."}
data: {"type": "done"}
```

---

## 🐳 Docker деплой

### Быстрый старт

```bash
# Запуск с Ollama
docker-compose up -d

# Проверка статуса
docker-compose ps

# Логи
docker-compose logs -f helix

# Остановка
docker-compose down
```

### Только Helix (без Ollama)

```bash
# Сборка
docker build -t helix:latest .

# Запуск
docker run -d \
  -p 8000:8000 \
  -e BASE_URL=http://your-llm-server:11434/v1 \
  -v $(pwd)/data:/app/data \
  --name helix \
  helix:latest
```

### Production деплой

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  helix:
    image: helix:latest
    restart: always
    environment:
      - REQUIRE_AUTH=true
      - MODEL=qwen2.5-coder:32b
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## 📊 Мониторинг и логирование

### Логи

Логи сохраняются в `logs/helix_YYYYMMDD.log` в JSON формате:

```json
{
  "timestamp": "2025-06-01T12:00:00.000000",
  "level": "INFO",
  "logger": "helix",
  "message": "Agent initialized",
  "module": "agent",
  "function": "initialize",
  "line": 42
}
```

### Метрики

```bash
# Получить метрики (требует admin права)
curl http://localhost:8000/admin/metrics \
  -H "Authorization: Bearer hx_admin_key"
```

Ответ:
```json
{
  "metrics": {
    "counters": {
      "requests": 150,
      "tool_calls": 320,
      "errors": 5,
      "skills_created": 12
    }
  },
  "summary": {
    "total_requests": 150,
    "total_tool_calls": 320,
    "avg_response_time": 2.5,
    "max_response_time": 8.3,
    "min_response_time": 0.5
  }
}
```

---

## 🛡️ Безопасность

### Command Whitelist

Только безопасные команды разрешены по умолчанию:

```python
from core.security.safety import command_whitelist

# Проверка команды
allowed, reason = command_whitelist.is_command_allowed("ls -la")
# (True, None)

allowed, reason = command_whitelist.is_command_allowed("rm -rf /")
# (False, "Blocked dangerous pattern: rm\\s+-rf")

# Добавить команду в whitelist
command_whitelist.add_to_whitelist("docker ps")
```

### Опасные команды блокируются

- `rm -rf` - рекурсивное удаление
- `dd` - операции с диском
- `shutdown`, `reboot` - перезагрузка системы
- `curl ... | sh` - выполнение скриптов из интернета
- Fork bombs и другие опасные паттерны

### Подтверждение пользователя

Некоторые операции требуют подтверждения:
- Удаление файлов (`rm`)
- Git push/commit
- Установка пакетов
- Docker операции

```python
from core.security.safety import confirmation_checker

if confirmation_checker.requires_confirmation("git push"):
    # Запросить подтверждение у пользователя
    ...
```

---

## 🧪 Тестирование

```bash
# Запуск всех тестов
pytest

# С подробным выводом
pytest -v

# Конкретный тест
pytest tests/test_tools.py::test_write_and_read_file

# С покрытием кода
pytest --cov=core --cov-report=html
```

Тесты покрывают:
- ✅ Инструменты (file ops, calculator, database)
- ✅ Систему памяти (SQLite + ChromaDB)
- ✅ Навыки (создание, загрузка, поиск)
- ✅ Аутентификацию (API ключи, permissions)

---

## 📝 Примеры использования

### 1. Поиск и анализ информации

```bash
python cli.py "Найди информацию о последних обновлениях Python и создай summary"
```

### 2. Работа с данными

```bash
python cli.py "Создай базу данных users.db с таблицей users (id, name, email) и добавь 5 записей"
```

### 3. Анализ кода

```bash
python cli.py "Проанализируй код в main.py и предложи улучшения"
```

### 4. Математика и вычисления

```bash
python cli.py "Вычисли первые 20 чисел Фибоначчи и найди их среднее значение"
```

### 5. Streaming запрос

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "messages": [{"role": "user", "content": "Напиши длинную статью о AI"}],
        "stream": True
    },
    stream=True
)

for line in response.iter_lines():
    if line:
        print(line.decode())
```

---

## 🔧 Конфигурация

### Переменные окружения

```env
# LLM
MODEL=qwen2.5-coder:32b
BASE_URL=http://localhost:11434/v1
API_KEY=ollama
TEMPERATURE=0.7

# Агент
MAX_STEPS=15
DATA_DIR=data

# Память
MEMORY_DB_PATH=data/memory/memory.db
VECTOR_DB_PATH=data/memory/vector_db

# Навыки
SKILLS_DIR=data/skills

# Безопасность (в api/gateway.py)
REQUIRE_AUTH=false  # true для продакшена
```

---

## 📈 Производительность

### Оптимизации

1. **ChromaDB** - быстрый семантический поиск
2. **Асинхронность** - все операции async
3. **Кэширование** - навыки загружаются один раз
4. **Streaming** - ответы в реальном времени
5. **Rate limiting** - защита от перегрузок

### Рекомендации

- Используй Docker для изоляции
- Включи аутентификацию в production
- Настрой rate limits по API ключам
- Мониторь метрики через `/admin/metrics`
- Ротируй логи (logrotate)

---

## 🤝 Вклад в проект

Все улучшения реализованы и готовы к использованию!

Если хочешь добавить что-то новое:
1. Создай новый инструмент в `core/tools/`
2. Зарегистрируй в `registry.py`
3. Добавь тесты в `tests/`
4. Обнови документацию

---

## 📚 Дополнительная информация

- [README.md](README.md) - основная документация
- [config.py](config.py) - конфигурация
- [tests/](tests/) - примеры тестов
- [docker-compose.yml](docker-compose.yml) - Docker setup

**Все функции протестированы и готовы к использованию! 🎉**
