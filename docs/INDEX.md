# 📑 Индекс документации Helix

## 🔍 Быстрый поиск

### По алфавиту

| A-G | H-N | O-Z |
|-----|-----|-----|
| [API Gateway](#api-gateway) | [Helix](#что-такое-helix) | [Ollama](#ollama) |
| [Agents](#агенты) | [Installation](#установка) | [OpenAI](#openai) |
| [Authentication](#аутентификация) | [LiteLLM](#litellm) | [Profiles](#профили) |
| [ChromaDB](#chromadb) | [Memory](#память) | [Skills](#навыки) |
| [CLI](#cli) | [Models](#модели) | [Tools](#инструменты) |
| [Docker](#docker) | [Multi-provider](#multi-provider) | [Troubleshooting](#решение-проблем) |

---

## 📚 Документы по темам

### 🚀 Начало работы

- **[START_HERE.md](START_HERE.md)** - Первые шаги с Helix
- **[guides/QUICKSTART.md](guides/QUICKSTART.md)** - 5-минутная установка и запуск
- **[guides/CLI_GUIDE.md](guides/CLI_GUIDE.md)** - Полное руководство по командной строке

### ⚙️ Настройка

- **[setup/MODELS_SETUP.md](setup/MODELS_SETUP.md)** - Подробная настройка провайдеров моделей
- **[QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md)** - Быстрая настройка модели по умолчанию
- **[DEFAULT_MODEL_README.md](DEFAULT_MODEL_README.md)** - Как работает выбор модели

### 🔧 Решение проблем

- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Все частые проблемы и решения
- **[troubleshooting/TOOLCALLING_FIX.md](troubleshooting/TOOLCALLING_FIX.md)** - Tool calling ошибки

### 📖 Справка

- **[reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md)** - Все возможности Helix
- **[reference/SUMMARY.md](reference/SUMMARY.md)** - Техническая документация
- **[reference/CLI_SUMMARY.md](reference/CLI_SUMMARY.md)** - Обзор CLI
- **[reference/FINAL_CHECKLIST.md](reference/FINAL_CHECKLIST.md)** - Чеклист функций

### 📅 История

- **[CHANGELOG.md](CHANGELOG.md)** - История изменений проекта

---

## 🎯 По функционалу

### Установка

→ [guides/QUICKSTART.md](guides/QUICKSTART.md#installation)

```bash
uv sync
uv pip install -e .
helix --help
```

### CLI

→ [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md)

**Основные команды:**
- `helix chat-command` - интерактивный чат
- `helix run "query"` - разовый запрос
- `helix models setup` - настройка моделей
- `helix config show` - показать конфигурацию

### Модели

→ [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md)

**Провайдеры:**
- Ollama (локальный)
- LiteLLM (множественные провайдеры)
- OpenAI (официальный API)
- Groq (быстрый inference)

### Память

→ [reference/SUMMARY.md](reference/SUMMARY.md#memory-system)

**Компоненты:**
- SQLite для истории диалогов
- ChromaDB для векторного поиска
- Семантический поиск

### Навыки

→ [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#skills-system)

**Возможности:**
- Автогенерация из успешных сессий
- Семантический поиск навыков
- Переиспользование паттернов

### Инструменты

→ [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#new-tools)

**Список инструментов:**
- Файловые операции
- Терминал
- Веб-поиск
- База данных
- Python executor
- Калькулятор

### API Gateway

→ [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md#api-gateway)

```bash
helix gateway-command
```

OpenAI-совместимый API на `http://localhost:8000`

### Docker

→ [reference/SUMMARY.md](reference/SUMMARY.md#docker)

```bash
docker-compose up -d
```

### Безопасность

→ [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#security-system)

**Компоненты:**
- API ключи
- Rate limiting
- Command whitelist
- Подтверждение операций

---

## 🔤 Глоссарий

### Агенты

**Основной агент (main)** - главный агент Helix, обрабатывающий все запросы

**Субагенты** - специализированные агенты для конкретных задач (code-reviewer, research, etc.)

→ [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md#configure-agent-models)

### Аутентификация

Система API ключей для доступа к API Gateway

→ [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#authentication)

### ChromaDB

Векторная база данных для семантического поиска

→ [reference/SUMMARY.md](reference/SUMMARY.md#memory-system)

### CLI

Command Line Interface - интерфейс командной строки

→ [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md)

### Docker

Контейнеризация для легкого развертывания

→ [reference/SUMMARY.md](reference/SUMMARY.md#docker)

### LiteLLM

Прокси для множественных LLM провайдеров

→ [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md#litellm)

### Memory

Система памяти Helix (SQLite + ChromaDB)

→ [reference/SUMMARY.md](reference/SUMMARY.md#memory-system)

### Models

LLM модели, используемые Helix

→ [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md)

### Multi-provider

Поддержка множественных провайдеров моделей

→ [QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md#multiple-providers)

### Ollama

Локальный LLM сервер

→ [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md#ollama)

### OpenAI

Официальный API от OpenAI

→ [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md#openai)

### Profiles

Профили конфигурации для разных контекстов

→ [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md#profiles)

### Skills

Навыки, автоматически генерируемые из успешных сессий

→ [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#skills-system)

### Tools

Инструменты для взаимодействия с системой

→ [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#new-tools)

---

## 🗺️ Карта документации

```
docs/
│
├── README.md                    # 📚 Главная навигация
├── INDEX.md                     # 📑 Этот файл - быстрый поиск
├── START_HERE.md                # 🚀 Начните здесь!
├── CHANGELOG.md                 # 📅 История изменений
│
├── QUICK_MODEL_SETUP.md        # 🎯 Быстрая настройка
├── DEFAULT_MODEL_README.md     # 📋 О моделях по умолчанию
├── TROUBLESHOOTING.md          # 🔧 Решение проблем
│
├── guides/                      # 📖 Руководства
│   ├── QUICKSTART.md           # ⚡ 5-минутный старт
│   └── CLI_GUIDE.md            # 💻 Полный CLI гайд
│
├── setup/                       # ⚙️ Настройка
│   └── MODELS_SETUP.md         # 🎯 Настройка моделей
│
├── troubleshooting/             # 🛠️ Решение проблем
│   └── TOOLCALLING_FIX.md      # 🔧 Tool calling ошибки
│
└── reference/                   # 📚 Справка
    ├── IMPROVEMENTS.md          # ✨ Все возможности
    ├── SUMMARY.md               # 📊 Техническое резюме
    ├── CLI_SUMMARY.md           # 📝 CLI обзор
    └── FINAL_CHECKLIST.md       # ✅ Чеклист
```

---

## 🔗 Внешние ссылки

- **GitHub:** https://github.com/yourrepo/helix
- **Issues:** https://github.com/yourrepo/helix/issues
- **LiteLLM:** https://litellm.ai
- **Ollama:** https://ollama.ai
- **ChromaDB:** https://www.trychroma.com

---

## 💡 Советы по поиску

### Ищете как...

**...установить?** → [guides/QUICKSTART.md](guides/QUICKSTART.md)

**...настроить модель?** → [QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md)

**...использовать CLI?** → [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md)

**...решить ошибку?** → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

**...создать навык?** → [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#skills-system)

**...работать с памятью?** → [reference/SUMMARY.md](reference/SUMMARY.md#memory-system)

**...настроить несколько провайдеров?** → [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md)

**...запустить в Docker?** → [reference/SUMMARY.md](reference/SUMMARY.md#docker)

---

**Последнее обновление:** 2025-06-01
**Версия:** 1.0
