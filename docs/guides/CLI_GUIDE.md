# Helix CLI - Руководство пользователя

## 🚀 Установка и первый запуск

### Установка зависимостей

```bash
uv sync
```

### Первый запуск

```bash
# Установить CLI команду
uv pip install -e .

# Или запустить напрямую
python -m cli.main --help
```

---

## 📚 Основные команды

### Интерактивный чат

```bash
# Запуск интерактивного чата
helix chat

# С другим профилем
helix chat --profile work

# С кастомными параметрами
helix chat --model gpt-4 --temperature 0.5
```

**Специальные команды в чате:**

- `/clear` - Очистить текущий диалог
- `/model <name>` - Сменить модель
- `/profile <name>` - Сменить профиль
- `/skills` - Показать активные навыки
- `/memory <query>` - Поиск по памяти
- `/status` - Показать статус
- `/help` - Справка
- `/exit` или `/quit` - Выход

### Одиночный запрос

```bash
# Выполнить запрос и выйти
helix run "Создай FastAPI endpoint для регистрации пользователей"

# С профилем
helix --profile work run "Проанализируй код в main.py"
```

### API Gateway

```bash
# Запустить API сервер
helix gateway

# На другом порту
helix gateway --port 3000

# С автоперезагрузкой
helix gateway --reload
```

---

## 🎭 Профили

Профили позволяют иметь раздельные настройки, память и навыки для разных задач.

### Работа с профилями

```bash
# Статус текущего профиля
helix status

# Использовать профиль
helix --profile work chat

# Список профилей
helix status  # Показывает все профили

# Очистить профиль
helix --profile work clear
```

### Структура профиля

Профили хранятся в `~/.helix/profiles/`:

```
~/.helix/
├── profiles/
│   ├── default/
│   │   ├── config.yaml
│   │   └── data/
│   │       ├── memory/
│   │       ├── skills/
│   │       └── security/
│   ├── work/
│   │   ├── config.yaml
│   │   └── data/
│   └── personal/
│       ├── config.yaml
│       └── data/
└── logs/
    ├── helix-default.log
    └── history_default.txt
```

### Конфигурация профиля

```yaml
# ~/.helix/profiles/work/config.yaml
model: qwen2.5-coder:32b
base_url: http://localhost:11434/v1
api_key: ollama
temperature: 0.7
max_steps: 15
profile_name: work
data_dir: ~/.helix/profiles/work/data
```

---

## 🛠️ Управление конфигурацией

### Просмотр конфигурации

```bash
# Показать текущую конфигурацию
helix config show

# Редактировать в редакторе
helix config edit
```

### Изменение настроек

```bash
# Изменить параметр
helix config set model gpt-4o
helix config set temperature 0.9
helix config set max_steps 20
```

---

## 💡 Навыки (Skills)

### Просмотр навыков

```bash
# Список всех навыков
helix skills list

# Ограничить вывод
helix skills list --limit 10

# Поиск навыков
helix skills search "fastapi"
helix skills search "database"

# Подробная информация
helix skills show create_fastapi_endpoint
```

### Навыки создаются автоматически

Helix автоматически создаёт навыки из успешных многошаговых задач.

Пример:
```bash
You: Создай FastAPI endpoint для регистрации пользователей с валидацией

# Helix выполнит задачу и создаст навык
# Файл: ~/.helix/profiles/default/data/skills/user_registration_endpoint.md
```

---

## 🔍 Поиск по памяти

```bash
# Поиск в памяти агента
helix memory search "как создать API"
helix memory search "FastAPI" --limit 5
```

В интерактивном режиме:
```
You: /memory как работать с базой данных
```

---

## 🎨 Красивый вывод

CLI использует **Rich** для профессионального вывода:

- ✅ Цветной текст
- ✅ Таблицы
- ✅ Панели
- ✅ Markdown рендеринг
- ✅ Спиннеры и прогресс-бары
- ✅ Подсветка синтаксиса

---

## 📋 Все доступные команды

```bash
helix --help                          # Общая справка
helix --profile work chat             # Чат с профилем
helix chat                            # Интерактивный чат
helix run "запрос"                    # Одиночный запрос
helix gateway                         # API сервер
helix status                          # Статус профиля
helix clear                           # Очистить профиль
helix models                          # Список моделей (Ollama)

helix skills list                     # Список навыков
helix skills search "query"           # Поиск навыков
helix skills show <name>              # Показать навык

helix memory search "query"           # Поиск в памяти

helix config show                     # Показать конфигурацию
helix config edit                     # Редактировать
helix config set <key> <value>        # Установить значение

helix version                         # Версия Helix
```

---

## 💻 Примеры использования

### Пример 1: Разработка на работе

```bash
# Создать рабочий профиль
helix --profile work chat

You: Создай структуру FastAPI проекта с аутентификацией
You: /skills  # Посмотреть созданные навыки
You: /model gpt-4o  # Сменить модель для сложной задачи
```

### Пример 2: Личные проекты

```bash
helix --profile personal run "Напиши Python скрипт для парсинга CSV"
```

### Пример 3: Поиск старых решений

```bash
helix memory search "как я делал аутентификацию"
```

### Пример 4: API для интеграции

```bash
# Запустить API на порту 8000
helix gateway --port 8000

# Использовать из другого приложения
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "conversation_id": "api_test"
  }'
```

---

## 🎯 Лучшие практики

### 1. Используйте профили для разных контекстов

```bash
helix --profile work       # Для работы
helix --profile personal   # Для личных проектов
helix --profile learning   # Для обучения
```

### 2. Переиспользуйте навыки

```bash
# Сначала найдите существующий навык
helix skills search "fastapi"

# Потом используйте в чате
You: Используя навык create_fastapi_endpoint, создай endpoint для удаления пользователя
```

### 3. Используйте память

```bash
# Ищите предыдущие решения
You: /memory как я решал задачу с аутентификацией
```

### 4. Настраивайте под задачу

```bash
# Для кода - низкая температура
helix chat --temperature 0.3

# Для креатива - высокая температура
helix chat --temperature 0.9
```

---

## 🐛 Troubleshooting

### CLI команда не найдена

```bash
# Переустановить
uv pip uninstall helix
uv pip install -e .

# Или использовать напрямую
python -m cli.main chat
```

### Ошибка импорта

```bash
# Убедитесь что все зависимости установлены
uv sync
```

### Профиль не найден

```bash
# Helix автоматически создаст профиль при первом использовании
helix --profile newprofile chat
```

### Очистить всё и начать заново

```bash
# Удалить данные профиля
rm -rf ~/.helix/profiles/default/data

# Или использовать команду
helix clear --yes
```

---

## 🎨 Кастомизация

### Изменить редактор для конфига

```bash
export EDITOR=vim
helix config edit
```

### Изменить домашнюю директорию

По умолчанию: `~/.helix`

Можно изменить в `cli/core.py`:
```python
HELIX_HOME = Path.home() / ".helix"
```

---

## 📖 Дополнительно

- [README.md](README.md) - Основная документация
- [QUICKSTART.md](QUICKSTART.md) - Быстрый старт
- [IMPROVEMENTS.md](IMPROVEMENTS.md) - Список улучшений

---

**Helix CLI готов к использованию! 🚀**

Начни с:
```bash
helix chat
```
