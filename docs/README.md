# 📚 Helix Documentation

Добро пожаловать в документацию **Helix** - самообучающегося AI агента с памятью и навыками!

## 🚀 Быстрый старт

**Новичок в Helix?** Начните здесь:

1. **[START_HERE.md](START_HERE.md)** - Введение и первые шаги (30 секунд)
2. **[guides/QUICKSTART.md](guides/QUICKSTART.md)** - 5-минутный быстрый старт

## 📖 Навигация по документации

### 🎯 Для начинающих

| Документ | Описание |
|----------|----------|
| **[START_HERE.md](START_HERE.md)** | 🚀 С чего начать - первое знакомство |
| **[guides/QUICKSTART.md](guides/QUICKSTART.md)** | ⚡ Быстрый старт за 5 минут |
| **[guides/CLI_GUIDE.md](guides/CLI_GUIDE.md)** | 💻 Полное руководство по CLI |

### ⚙️ Настройка и конфигурация

| Документ | Описание |
|----------|----------|
| **[setup/MODELS_SETUP.md](setup/MODELS_SETUP.md)** | 🎯 Настройка провайдеров и моделей |
| **[QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md)** | 🚀 Быстрая настройка модели по умолчанию |
| **[DEFAULT_MODEL_README.md](DEFAULT_MODEL_README.md)** | 📋 Подробно о моделях по умолчанию |

### 🔧 Решение проблем

| Документ | Описание |
|----------|----------|
| **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** | 🔧 Частые проблемы и решения |
| **[troubleshooting/TOOLCALLING_FIX.md](troubleshooting/TOOLCALLING_FIX.md)** | 🛠️ Исправление ошибок tool calling |

### 📚 Справочная информация

| Документ | Описание |
|----------|----------|
| **[reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md)** | ✨ Все возможности Helix |
| **[reference/SUMMARY.md](reference/SUMMARY.md)** | 📊 Техническое резюме проекта |
| **[reference/CLI_SUMMARY.md](reference/CLI_SUMMARY.md)** | 📝 Обзор CLI имплементации |
| **[reference/FINAL_CHECKLIST.md](reference/FINAL_CHECKLIST.md)** | ✅ Чеклист реализованных функций |
| **[CHANGELOG.md](CHANGELOG.md)** | 📅 История изменений |

---

## 🎓 Треки обучения

### Трек 1: Быстрый старт (15 минут)

Для тех, кто хочет быстро начать работать:

1. 📖 [START_HERE.md](START_HERE.md) - Прочитать введение (2 мин)
2. ⚡ [guides/QUICKSTART.md](guides/QUICKSTART.md) - Установить и запустить (5 мин)
3. 🎯 [QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md) - Настроить модель (5 мин)
4. 💬 Запустить первый чат: `helix chat-command`

**Результат:** Вы можете использовать Helix для базовых задач.

---

### Трек 2: Полное освоение (1 час)

Для тех, кто хочет использовать все возможности:

1. 📖 [START_HERE.md](START_HERE.md) - Введение (5 мин)
2. 💻 [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md) - Все CLI команды (15 мин)
3. 🎯 [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md) - Настройка моделей (15 мин)
4. ✨ [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md) - Возможности (15 мин)
5. 🔧 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - На всякий случай (10 мин)

**Результат:** Вы эксперт в Helix и можете настроить всё под себя.

---

### Трек 3: Для разработчиков (2 часа)

Для тех, кто хочет расширить или модифицировать Helix:

1. 📊 [reference/SUMMARY.md](reference/SUMMARY.md) - Архитектура (20 мин)
2. 📝 [reference/CLI_SUMMARY.md](reference/CLI_SUMMARY.md) - CLI структура (15 мин)
3. ✅ [reference/FINAL_CHECKLIST.md](reference/FINAL_CHECKLIST.md) - Что реализовано (10 мин)
4. 🎯 [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md) - Система моделей (20 мин)
5. 📖 Исходный код в `core/`, `cli/`, `api/` (оставшееся время)

**Результат:** Вы понимаете архитектуру и можете создавать свои инструменты и навыки.

---

## 🗂️ Структура документации

```
docs/
├── README.md                           # 📚 Этот файл - навигация
├── START_HERE.md                       # 🚀 Начните здесь!
├── CHANGELOG.md                        # 📅 История изменений
├── QUICK_MODEL_SETUP.md               # 🎯 Быстрая настройка моделей
├── DEFAULT_MODEL_README.md            # 📋 Модели по умолчанию
├── TROUBLESHOOTING.md                 # 🔧 Решение проблем
│
├── guides/                            # 📖 Руководства
│   ├── QUICKSTART.md                  # ⚡ 5-минутный старт
│   └── CLI_GUIDE.md                   # 💻 Полное руководство по CLI
│
├── setup/                             # ⚙️ Настройка
│   └── MODELS_SETUP.md                # 🎯 Настройка провайдеров моделей
│
├── troubleshooting/                   # 🛠️ Исправление ошибок
│   └── TOOLCALLING_FIX.md            # 🔧 Tool calling проблемы
│
└── reference/                         # 📚 Справка
    ├── IMPROVEMENTS.md                # ✨ Все возможности
    ├── SUMMARY.md                     # 📊 Техническое резюме
    ├── CLI_SUMMARY.md                 # 📝 CLI обзор
    └── FINAL_CHECKLIST.md            # ✅ Чеклист функций
```

---

## 🔍 Найти что-то конкретное

### По функциям

| Что вы хотите сделать? | Читайте |
|------------------------|---------|
| Установить Helix | [guides/QUICKSTART.md](guides/QUICKSTART.md) |
| Запустить чат | [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md#interactive-chat) |
| Настроить модель | [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md) |
| Подключить LiteLLM | [QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md) |
| Создать навыки | [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#skills-system) |
| Работать с памятью | [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md#memory-commands) |
| Запустить API Gateway | [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md#api-gateway) |
| Решить проблему | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |

### По компонентам

| Компонент | Документация |
|-----------|-------------|
| **CLI** | [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md) |
| **Модели** | [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md) |
| **Tools** | [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#new-tools) |
| **Memory** | [reference/SUMMARY.md](reference/SUMMARY.md#memory-system) |
| **Skills** | [reference/SUMMARY.md](reference/SUMMARY.md#skills-system) |
| **API** | [reference/SUMMARY.md](reference/SUMMARY.md#api-gateway) |
| **Security** | [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md#security-system) |

---

## ❓ Частые вопросы

### Как установить?

```bash
git clone <repo>
cd Helix
uv sync
uv pip install -e .
helix --help
```

Подробнее: [guides/QUICKSTART.md](guides/QUICKSTART.md)

### Как настроить модель?

```bash
helix models setup
```

Подробнее: [QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md)

### Ошибка tool calling?

Используйте модель с поддержкой tool calling: `smart`, `claude-sonnet-4-6`, `gpt-4o`

Подробнее: [troubleshooting/TOOLCALLING_FIX.md](troubleshooting/TOOLCALLING_FIX.md)

### Где конфигурация?

```
~/.helix/profiles/default/config.yaml
```

Подробнее: [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md#configuration)

---

## 🚀 Быстрые команды

```bash
# Первый запуск
helix chat-command

# Настройка моделей
helix models setup

# Статус
helix status

# Помощь
helix --help
helix models --help

# Конфигурация
helix config show
helix config edit
```

---

## 🤝 Вклад и обратная связь

- **GitHub Issues:** [Сообщить о проблеме](https://github.com/yourrepo/helix/issues)
- **Документация:** Этот репозиторий
- **Примеры:** См. [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md)

---

## 📄 Лицензия

MIT License - см. LICENSE файл

---

**Последнее обновление:** 2025-06-01
**Версия Helix:** 0.1.0
**Версия документации:** 1.0
