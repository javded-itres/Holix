# 🚀 START HERE - Helix AI Agent

## Что такое Helix?

**Helix** - это самообучающийся AI-агент с памятью, навыками и профессиональным CLI интерфейсом.

Думай о нём как о **ChatGPT + долговременная память + автоматическое создание навыков + инструменты + красивый CLI**.

---

## ⚡ Быстрый старт (30 секунд)

```bash
# 1. Установка
uv sync && uv pip install -e .

# 2. Запуск
helix chat

# 3. Попробуй
You: Создай FastAPI endpoint для регистрации пользователей
```

**Готово!** Helix теперь работает.

---

## 🎯 Что умеет Helix?

### 1. **10+ Мощных инструментов**

```bash
You: Найди в интернете последнюю версию Python
# Использует web_search

You: Создай базу данных users.db с таблицей users
# Использует sql_query

You: Вычисли факториал 20
# Использует calculate
```

**Доступные инструменты:**
- 🌐 `web_search` - поиск в интернете
- 🌍 `fetch_url` - загрузка URL
- 💾 `sql_query` - работа с SQLite
- 🐍 `execute_python` - запуск Python кода
- 🧮 `calculate` - математика
- 📁 `read_file`, `write_file`, `list_directory`
- 💻 `run_terminal_command`

### 2. **Самообучение**

Helix автоматически создаёт навыки из успешных задач:

```bash
You: Создай REST API endpoint для CRUD операций с пользователями

# Helix выполняет задачу и создаёт навык
# Файл: ~/.helix/profiles/default/data/skills/crud_api_endpoint.md

# В следующий раз:
You: Создай CRUD endpoint для продуктов
# Helix использует навык "crud_api_endpoint" и делает быстрее!
```

### 3. **Долговременная память**

```bash
You: /memory как я делал аутентификацию в прошлый раз

# Helix ищет по всей истории и находит решение
```

### 4. **Профили для разных контекстов**

```bash
# Работа
helix --profile work chat

# Личные проекты
helix --profile personal chat

# Эксперименты
helix --profile experiments chat
```

Каждый профиль имеет:
- Свои настройки (модель, температура)
- Свою память
- Свои навыки
- Свою изоляцию

---

## 🎨 Профессиональный CLI

### Красивый интерфейс

```
██╗  ██╗███████╗██╗     ██╗██╗  ██╗
██║  ██║██╔════╝██║     ██║╚██╗██╔╝
███████║█████╗  ██║     ██║ ╚███╔╝
██╔══██║██╔══╝  ██║     ██║ ██╔██╗
██║  ██║███████╗███████╗██║██╔╝ ██╗
╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝  ╚═╝

Self-Improving AI Agent • Profile: default • v0.1.0
```

### Возможности CLI

✅ **Typer + Rich** - премиальный UX
✅ **Markdown рендеринг** - красивые ответы с подсветкой кода
✅ **История команд** - стрелки вверх/вниз
✅ **Автодополнение** - быстрый ввод
✅ **Цветовой вывод** - cyan/green/red/yellow
✅ **Таблицы и панели** - структурированная информация
✅ **Спиннеры** - "Helix is thinking..."

### Специальные команды

Прямо в чате:

```bash
/clear      # Очистить диалог
/model      # Сменить модель
/profile    # Сменить профиль
/skills     # Показать навыки
/memory     # Поиск в памяти
/status     # Статус
/help       # Справка
/exit       # Выход
```

---

## 📚 Основные команды

```bash
# Интерактивный чат
helix chat
helix --profile work chat

# Одиночный запрос
helix run "Создай парсер CSV файлов"

# API сервер
helix gateway --port 8000

# Управление навыками
helix skills list
helix skills search "fastapi"
helix skills show create_fastapi_endpoint

# Поиск в памяти
helix memory search "authentication"

# Конфигурация
helix config show
helix config edit
helix config set temperature 0.9

# Статус
helix status
helix models
helix version
```

---

## 🔥 Примеры использования

### Пример 1: Создание API

```bash
helix chat

You: Создай FastAPI приложение с:
- Endpoint для регистрации пользователей
- Валидация email
- Хэширование паролей
- SQLite база данных

# Helix создаёт полное решение за 30 секунд
```

### Пример 2: Анализ кода

```bash
helix run "Прочитай main.py и предложи улучшения производительности"
```

### Пример 3: Поиск информации

```bash
You: Найди последние новости о Python 3.13 и создай краткую сводку

# Helix:
# 1. Использует web_search
# 2. Находит статьи
# 3. Анализирует
# 4. Создаёт сводку
```

### Пример 4: Работа с данными

```bash
You: Создай БД users.db, добавь таблицу и 10 тестовых записей

# Helix использует sql_query и создаёт навык
```

---

## 🎓 Куда смотреть дальше?

### Быстрое изучение

1. **[QUICKSTART.md](QUICKSTART.md)** - начни отсюда (5 минут)
2. **[CLI_GUIDE.md](CLI_GUIDE.md)** - полное руководство по CLI (10 минут)

### Детальная документация

3. **[README.md](README.md)** - техническая документация
4. **[IMPROVEMENTS.md](IMPROVEMENTS.md)** - все новые функции
5. **[CLI_SUMMARY.md](CLI_SUMMARY.md)** - обзор CLI

### Для разработчиков

6. **[SUMMARY.md](SUMMARY.md)** - полный технический отчёт
7. **[FINAL_CHECKLIST.md](FINAL_CHECKLIST.md)** - что реализовано

---

## 💡 Советы для начала

### 1. Начни с профиля

```bash
# Создай профиль для работы
helix --profile work chat

You: Я занимаюсь веб-разработкой на Python
# Helix запомнит контекст
```

### 2. Экспериментируй с командами

```bash
You: /skills  # Посмотри какие навыки есть
You: /model gpt-4o  # Попробуй другую модель
You: /status  # Проверь настройки
```

### 3. Используй память

```bash
You: /memory fastapi
# Найдёт всё что ты делал с FastAPI раньше
```

### 4. Создавай навыки

Просто решай сложные задачи - Helix автоматически создаст навыки!

---

## 🔧 Настройка под себя

### Модель

```bash
# В чате
You: /model qwen2.5-coder:32b
You: /model gpt-4o

# Или в конфиге
helix config set model gpt-4o
```

### Температура

```bash
# Для кода (точность)
helix config set temperature 0.3

# Для креатива (разнообразие)
helix config set temperature 0.9
```

### Профили

```bash
# Рабочий - точная модель
helix --profile work config set model qwen2.5-coder:32b
helix --profile work config set temperature 0.3

# Личный - креативная модель
helix --profile personal config set model gpt-4o
helix --profile personal config set temperature 0.7
```

---

## 🐳 Docker (опционально)

```bash
# Запуск с Ollama
docker-compose up -d

# Проверка
curl http://localhost:8000/health

# Логи
docker-compose logs -f helix
```

---

## 🎯 Что дальше?

1. **Запусти:** `helix chat`
2. **Попробуй инструменты:** поиск в интернете, работа с БД, вычисления
3. **Создай навыки:** реши несколько сложных задач
4. **Используй профили:** раздели работу и личное
5. **Экспериментируй:** пробуй разные модели и настройки

---

## 💬 Нужна помощь?

```bash
# В CLI
helix --help
helix chat --help

# В чате
You: /help

# Документация
cat CLI_GUIDE.md
cat QUICKSTART.md
```

---

## 🎉 Готов начать!

```bash
helix chat
```

**Добро пожаловать в Helix! 🚀**

---

## 📊 Краткая статистика

- **10+ инструментов** (веб, БД, код, файлы)
- **Автоматическое обучение** через навыки
- **Долговременная память** (SQLite + ChromaDB)
- **Профили** для разных контекстов
- **Премиальный CLI** (Typer + Rich)
- **API Gateway** (OpenAI-compatible)
- **Production-ready** (Docker, security, monitoring)

**Версия:** 0.1.0
**Статус:** Production Ready ✅
**Качество:** ⭐⭐⭐⭐⭐

---

**Создано с ❤️ для продуктивной работы с AI**
