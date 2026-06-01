# 🤖 Helix - Self-Improving AI Agent

**Helix** - мощный самообучающийся AI агент с памятью, навыками и возможностью вызова инструментов. Он учится на успешных задачах и создаёт переиспользуемые навыки для будущего.

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](docs/CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## ✨ Возможности

- 🛠️ **Tool Calling** - Выполнение команд, работа с файлами, поиск в интернете
- 🧠 **Persistent Memory** - SQLite + ChromaDB для истории и семантического поиска
- 📚 **Skills System** - Автоматическое создание навыков из успешных сессий
- 🔄 **Self-Improvement** - Обучение на опыте
- 🌐 **API Gateway** - OpenAI-совместимый API
- 💻 **Professional CLI** - Красивый интерфейс командной строки
- 🔒 **Security** - Аутентификация, rate limiting, whitelist команд
- 🎯 **Multi-Provider** - Поддержка Ollama, LiteLLM, OpenAI, Groq и других

---

## 🚀 Быстрый старт

### 1. Установка

```bash
# Клонировать репозиторий
git clone <repo-url>
cd Helix

# Установить зависимости
uv sync

# Установить как пакет
uv pip install -e .
```

### 2. Настройка модели

```bash
# Интерактивная настройка
helix models setup

# Или отредактировать конфигурацию
helix config edit
```

### 3. Запуск

```bash
# Интерактивный чат
helix chat-command

# Разовый запрос
helix run "What is 2+2?"

# API Gateway
helix gateway-command
```

**Подробнее:** [📖 docs/START_HERE.md](docs/START_HERE.md)

---

## 📚 Документация

### 🎯 Начало работы

| Документ | Описание |
|----------|----------|
| **[START_HERE](docs/START_HERE.md)** | 🚀 С чего начать |
| **[QUICKSTART](docs/guides/QUICKSTART.md)** | ⚡ 5-минутный гайд |
| **[CLI_GUIDE](docs/guides/CLI_GUIDE.md)** | 💻 Полное руководство по CLI |

### ⚙️ Настройка

| Документ | Описание |
|----------|----------|
| **[MODELS_SETUP](docs/setup/MODELS_SETUP.md)** | 🎯 Настройка провайдеров |
| **[QUICK_MODEL_SETUP](docs/QUICK_MODEL_SETUP.md)** | 🚀 Быстрая настройка |

### 🔧 Помощь

| Документ | Описание |
|----------|----------|
| **[TROUBLESHOOTING](docs/TROUBLESHOOTING.md)** | 🔧 Решение проблем |
| **[TOOLCALLING_FIX](docs/troubleshooting/TOOLCALLING_FIX.md)** | 🛠️ Tool calling ошибки |

**Все документы:** [📂 docs/README.md](docs/README.md)

---

## 🎯 Примеры использования

### Интерактивный чат

```bash
helix chat-command
```

```
❯ Создай Python скрипт для парсинга JSON

🤖 Helix: [создаёт файл parser.py с кодом]

❯ /skills
📚 Доступные навыки:
1. json_parsing (созданный только что)

❯ /memory парсинг
🔍 Найдено в памяти: ...
```

### Разовые запросы

```bash
helix run "Покажи структуру проекта"
```

### API Gateway

```bash
# Запустить сервер
helix gateway-command

# В другом терминале
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "smart",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## 🏗️ Архитектура

```
Helix/
├── core/                      # Ядро агента
│   ├── agent.py              # Главный класс агента
│   ├── loop.py               # Цикл выполнения
│   ├── tools/                # Система инструментов (10+ tools)
│   ├── memory/               # SQLite + ChromaDB
│   ├── skills/               # Система навыков
│   ├── models/               # Управление моделями ⭐
│   └── security/             # Безопасность
│
├── cli/                      # CLI интерфейс
│   ├── main.py              # Точка входа
│   ├── commands/            # Команды (chat, run, models...)
│   └── utils/               # Утилиты (rich, banner)
│
├── api/                      # API Gateway
│   ├── gateway.py           # FastAPI сервер
│   └── models.py            # Pydantic модели
│
├── docs/                     # Документация 📚
│   ├── README.md            # Навигация
│   ├── guides/              # Руководства
│   ├── setup/               # Настройка
│   ├── troubleshooting/     # Решение проблем
│   └── reference/           # Справка
│
└── tests/                    # Тесты
```

---

## 🛠️ Основные команды

```bash
# Чат
helix chat-command              # Интерактивный чат
helix run "query"              # Разовый запрос

# Модели
helix models setup             # Настроить провайдеры
helix models list              # Список провайдеров
helix models agents            # Модели для агентов

# Конфигурация
helix config show              # Показать конфигурацию
helix config edit              # Редактировать

# Навыки и память
helix skills list              # Список навыков
helix memory search "query"    # Поиск в памяти

# Информация
helix status                   # Статус профиля
helix --help                   # Помощь
```

---

## 🎯 Система моделей

Helix поддерживает множественные провайдеры:

```yaml
# ~/.helix/profiles/default/config.yaml

default_provider: litellm

providers:
  litellm:
    base_url: http://192.168.88.252:4000/v1
    api_key: sk-1234567890abcdef
    default_model: smart
    available_models: [smart, fast, heavy, coder, ...]

  ollama:
    base_url: http://localhost:11434/v1
    default_model: qwen2.5-coder:32b

agent_models:
  main:
    provider: litellm
    model: smart

  code-reviewer:
    provider: litellm
    model: heavy
```

**Подробнее:** [docs/setup/MODELS_SETUP.md](docs/setup/MODELS_SETUP.md)

---

## 🌟 Ключевые особенности

### 🛠️ 10+ Инструментов

- ✅ Чтение/запись файлов
- ✅ Выполнение команд
- ✅ Поиск в интернете
- ✅ Работа с базами данных
- ✅ Выполнение Python кода
- ✅ Математические вычисления

### 🧠 Умная память

- **SQLite** - История диалогов
- **ChromaDB** - Векторный поиск
- **Semantic Search** - Поиск по смыслу

### 📚 Система навыков

- Автогенерация из успешных сессий
- Семантический поиск навыков
- Переиспользование паттернов

### 🔒 Безопасность

- API ключи с SHA-256 хешированием
- Rate limiting
- Whitelist команд
- Подтверждение опасных операций

---

## 🐳 Docker

```bash
# С docker-compose
docker-compose up -d

# Только Helix
docker build -t helix .
docker run -p 8000:8000 helix
```

---

## 🤝 Вклад

Мы приветствуем вклад! Пожалуйста:

1. Fork репозиторий
2. Создайте feature branch
3. Commit изменения
4. Push в branch
5. Создайте Pull Request

---

## 📄 Лицензия

MIT License - см. [LICENSE](LICENSE)

---

## 📞 Контакты и поддержка

- **Документация:** [docs/README.md](docs/README.md)
- **Issues:** [GitHub Issues](https://github.com/yourrepo/helix/issues)
- **Примеры:** [docs/guides/](docs/guides/)

---

## 🎓 Изучение

### Для пользователей

1. [START_HERE.md](docs/START_HERE.md) - Введение
2. [QUICKSTART.md](docs/guides/QUICKSTART.md) - Быстрый старт
3. [CLI_GUIDE.md](docs/guides/CLI_GUIDE.md) - Все команды

### Для разработчиков

1. [SUMMARY.md](docs/reference/SUMMARY.md) - Архитектура
2. [IMPROVEMENTS.md](docs/reference/IMPROVEMENTS.md) - Возможности
3. Исходный код в `core/`, `cli/`, `api/`

---

## 📊 Статистика проекта

- **Язык:** Python 3.14+
- **Строк кода:** ~5,000+
- **Модулей:** 50+
- **Инструментов:** 10+
- **API endpoints:** 15+
- **CLI команд:** 20+
- **Документов:** 15+

---

## 🗺️ Roadmap

- [ ] Web UI
- [ ] Больше инструментов
- [ ] Плагинная система
- [ ] Multi-agent collaboration
- [ ] RAG интеграция
- [ ] Fine-tuning поддержка

---

**Версия:** 0.1.0
**Дата:** 2025-06-01
**Автор:** Helix Team

**Начните сейчас:** `helix chat-command` 🚀
