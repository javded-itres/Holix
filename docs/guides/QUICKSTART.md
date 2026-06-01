# Helix - Быстрый старт

## 🚀 Установка и запуск за 5 минут

### Вариант 1: Локальная установка

```bash
# 1. Установить зависимости
uv sync

# 2. Создать .env файл
cp .env.example .env

# 3. Запустить Ollama (если используешь локальную LLM)
ollama serve
ollama pull qwen2.5-coder:32b

# 4. Запустить CLI
python cli.py
```

### Вариант 2: Docker

```bash
# Запуск с Ollama
docker-compose up -d

# Проверка
curl http://localhost:8000/health
```

---

## 💬 Первые команды

### CLI режим

```bash
# Интерактивный режим
python cli.py

# Специальные команды
history   # Показать историю
skills    # Список навыков
tools     # Список инструментов
exit      # Выход

# Примеры запросов
You: Покажи файлы в текущей директории
You: Создай файл test.py с функцией hello_world
You: Найди в интернете последнюю версию FastAPI
```

### API режим

```bash
# Запустить сервер
uvicorn api.gateway:app --reload --port 8000

# Тестовый запрос
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Привет!"}],
    "conversation_id": "test"
  }'
```

---

## 🔧 Основные возможности

### 1. Инструменты (10+)

| Инструмент | Описание |
|------------|----------|
| `read_file` | Чтение файлов |
| `write_file` | Создание/изменение файлов |
| `run_terminal_command` | Выполнение команд |
| `web_search` | Поиск в интернете (DuckDuckGo) |
| `fetch_url` | Загрузка URL |
| `sql_query` | Запросы к SQLite |
| `execute_python` | Запуск Python кода |
| `calculate` | Математические вычисления |

### 2. Память

- **SQLite** - история диалогов
- **ChromaDB** - семантический поиск
- **Markdown** - экспорт в читаемом формате

### 3. Навыки (Skills)

Агент автоматически создаёт навыки из успешных задач:

```markdown
# data/skills/create_fastapi_endpoint.md
---
name: create_fastapi_endpoint
description: Создание REST API endpoint в FastAPI
tags: [fastapi, python, web]
success_count: 5
---

## Шаги
1. Определить метод (GET/POST/PUT/DELETE)
2. Создать Pydantic модели
3. Реализовать handler функцию
4. Добавить в app
```

---

## 🔐 Безопасность (опционально)

### Включить аутентификацию

```python
# В api/gateway.py
REQUIRE_AUTH = True
```

### Создать первый API ключ

```bash
curl -X POST http://localhost:8000/admin/api-keys \
  -d "name=admin&permissions=read,write,admin&rate_limit=1000"
```

Сохрани полученный ключ:
```
hx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Использовать ключ

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer hx_xxxxx" \
  -d '...'
```

---

## 📊 Мониторинг

### Метрики

```bash
curl http://localhost:8000/admin/metrics
```

### Логи

```bash
# Смотреть логи
tail -f logs/helix_$(date +%Y%m%d).log

# В Docker
docker-compose logs -f helix
```

---

## 🎯 Примеры задач

### Задача 1: Анализ кода

```
You: Прочитай файл main.py и найди потенциальные проблемы
```

Агент:
1. Использует `read_file` для чтения
2. Анализирует код
3. Предлагает улучшения
4. Может создать навык "code_review"

### Задача 2: Поиск информации

```
You: Найди последние новости о Python 3.13 и создай краткую сводку
```

Агент:
1. `web_search` - поиск
2. `fetch_url` - загрузка статей
3. Анализ и сводка
4. Сохранение в память

### Задача 3: Работа с данными

```
You: Создай БД users.db, добавь таблицу и 5 записей
```

Агент:
1. `sql_query` - создание таблицы
2. `sql_query` - вставка данных
3. `sql_schema` - проверка
4. Создание навыка "sqlite_operations"

---

## 🐛 Troubleshooting

### Ошибка: ChromaDB не запускается

```bash
# Удалить старую БД
rm -rf data/memory/vector_db data/memory/skills_db

# Перезапустить
python cli.py
```

### Ошибка: Ollama не отвечает

```bash
# Проверить статус
curl http://localhost:11434/api/tags

# Перезапустить
ollama serve
```

### Ошибка: Нет прав на выполнение

```bash
# CLI
chmod +x cli.py

# Проверить whitelist
# В core/security/safety.py добавь команду
```

---

## 📚 Дальнейшее чтение

- [README.md](README.md) - полная документация
- [IMPROVEMENTS.md](IMPROVEMENTS.md) - все новые функции
- [tests/](tests/) - примеры тестов
- [api/gateway.py](api/gateway.py) - API endpoints

---

## 🎉 Готово!

Ты готов использовать Helix! Попробуй:

```bash
python cli.py "Покажи мне что ты умеешь"
```

Агент покажет свои возможности и создаст первые навыки! 🚀
