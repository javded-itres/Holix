# Changelog

Все значимые изменения в проекте Helix будут документироваться здесь.

## [Unreleased]

### Добавлено
- 🎯 **Система множественных провайдеров моделей**
  - Поддержка OpenAI-совместимых API (Ollama, LiteLLM, OpenAI, Groq, etc.)
  - Автообнаружение доступных моделей
  - Интерактивная настройка через `helix models setup`
  - Назначение разных моделей для разных агентов/субагентов
  - Сохранение провайдеров в профилях

- 📦 **Новые модули**
  - `core/models/provider.py` - управление провайдерами
  - `core/models/discovery.py` - обнаружение моделей
  - `core/models/selector.py` - маршрутизация моделей

- 🎨 **CLI команды**
  - `helix models setup` - интерактивный мастер настройки
  - `helix models list` - список провайдеров
  - `helix models agents` - назначения моделей агентам

- 📚 **Документация**
  - `MODELS_SETUP.md` - полное руководство по настройке моделей
  - Примеры конфигурации для популярных провайдеров
  - Best practices и troubleshooting

### Исправлено
- 🐛 Ошибка `Progress.update() missing 1 required positional argument: 'task_id'`
  - Исправлена функция `create_spinner()` в `cli/utils/rich_console.py`
  - Обновлено использование во всех командах (`models.py`, `run.py`, `chat.py`)
  - Теперь правильно создается task с `progress.add_task()`

- 📝 Обновлена структура `ProfileConfig`
  - Добавлены поля `providers`, `agent_models`, `default_provider`
  - Поддержка хранения множественных провайдеров

### Изменено
- 🔧 Функция `create_spinner()` теперь не принимает аргумент `text`
  - Текст задачи передается через `progress.add_task(description, total=None)`
  - Обновлена документация в docstring

## [0.1.0] - 2025-06-01

### Добавлено
- 🚀 Начальный релиз Helix AI Agent
- 🛠️ Система инструментов (10+ tools)
- 🧠 Система памяти (SQLite + ChromaDB)
- 📚 Система навыков с автогенерацией
- 🔄 Self-improvement loop
- 🌐 API Gateway (FastAPI)
- 🎨 Professional CLI (Typer + Rich)
- 🔒 Система безопасности и аутентификации
- 📊 Мониторинг и логирование
- 🐳 Docker containerization
- 📖 Comprehensive documentation

---

**Формат:** [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/)
**Версионирование:** [Semantic Versioning](https://semver.org/lang/ru/)
