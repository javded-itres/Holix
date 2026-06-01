# 🧭 Навигатор по документации Helix

## Где что находится?

### 📍 Я хочу...

| Что вы хотите сделать? | Документ | Время |
|------------------------|----------|-------|
| **Установить Helix** | [guides/QUICKSTART.md](guides/QUICKSTART.md) | 5 мин |
| **Первое знакомство** | [START_HERE.md](START_HERE.md) | 2 мин |
| **Запустить чат** | [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md#chat) | 1 мин |
| **Настроить модель** | [QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md) | 5 мин |
| **Подключить LiteLLM** | [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md#litellm) | 10 мин |
| **Решить ошибку** | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | зависит |
| **Увидеть все возможности** | [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md) | 15 мин |
| **Понять архитектуру** | [reference/SUMMARY.md](reference/SUMMARY.md) | 20 мин |

---

## 🎯 Я...

### Новичок

**Ваш путь (30 минут):**

1. ✅ [START_HERE.md](START_HERE.md) - Что такое Helix? (5 мин)
2. ✅ [guides/QUICKSTART.md](guides/QUICKSTART.md) - Установка (10 мин)
3. ✅ [QUICK_MODEL_SETUP.md](QUICK_MODEL_SETUP.md) - Настройка (10 мин)
4. ✅ Запустить: `helix chat-command` (5 мин)

**Результат:** Вы можете использовать Helix!

---

### Продвинутый пользователь

**Ваш путь (1 час):**

1. ✅ [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md) - Все команды (20 мин)
2. ✅ [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md) - Multi-provider (20 мин)
3. ✅ [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md) - Возможности (20 мин)

**Результат:** Вы эксперт Helix!

---

### Разработчик

**Ваш путь (2 часа):**

1. ✅ [reference/SUMMARY.md](reference/SUMMARY.md) - Архитектура (30 мин)
2. ✅ [reference/CLI_SUMMARY.md](reference/CLI_SUMMARY.md) - CLI код (20 мин)
3. ✅ Исходники `core/`, `cli/`, `api/` (остальное время)

**Результат:** Вы можете расширить Helix!

---

## 🔍 У меня проблема...

### Tool calling ошибки

→ [troubleshooting/TOOLCALLING_FIX.md](troubleshooting/TOOLCALLING_FIX.md)

**Быстрое решение:**
```bash
helix config edit
# Измените default_model на: smart
```

---

### Connection refused

→ [TROUBLESHOOTING.md](TROUBLESHOOTING.md#connection-errors)

**Проверка:**
```bash
curl http://192.168.88.252:4000/v1/models
```

---

### Модель не найдена

→ [TROUBLESHOOTING.md](TROUBLESHOOTING.md#model-not-found)

**Решение:**
```bash
helix models setup
# Выбрать: 3. Test provider connection
```

---

### Все остальные проблемы

→ [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## 📚 По компонентам

| Компонент | Документ | Раздел |
|-----------|----------|--------|
| **CLI** | [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md) | Команды |
| **Модели** | [setup/MODELS_SETUP.md](setup/MODELS_SETUP.md) | Настройка |
| **Tools** | [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md) | New Tools |
| **Memory** | [reference/SUMMARY.md](reference/SUMMARY.md) | Memory System |
| **Skills** | [reference/SUMMARY.md](reference/SUMMARY.md) | Skills System |
| **API** | [guides/CLI_GUIDE.md](guides/CLI_GUIDE.md) | Gateway |
| **Security** | [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md) | Security |
| **Docker** | [reference/SUMMARY.md](reference/SUMMARY.md) | Docker |

---

## 🗺️ Карта сайта

```
📚 Документация Helix
│
├── 🏠 Главная страница
│   └── README.md - Обзор всей документации
│
├── 🔍 Поиск
│   ├── INDEX.md - Алфавитный указатель
│   └── NAVIGATION.md - Этот файл
│
├── 🚀 Быстрый старт
│   ├── START_HERE.md - Начните здесь
│   ├── guides/QUICKSTART.md - 5 минут до запуска
│   └── QUICK_MODEL_SETUP.md - Настройка модели
│
├── 📖 Руководства
│   └── guides/CLI_GUIDE.md - Полный CLI гайд
│
├── ⚙️ Настройка
│   ├── setup/MODELS_SETUP.md - Провайдеры моделей
│   └── DEFAULT_MODEL_README.md - О моделях
│
├── 🔧 Решение проблем
│   ├── TROUBLESHOOTING.md - Все проблемы
│   └── troubleshooting/TOOLCALLING_FIX.md - Tool calling
│
├── 📚 Справка
│   ├── reference/IMPROVEMENTS.md - Возможности
│   ├── reference/SUMMARY.md - Архитектура
│   ├── reference/CLI_SUMMARY.md - CLI обзор
│   └── reference/FINAL_CHECKLIST.md - Чеклист
│
└── 📅 История
    └── CHANGELOG.md - Изменения
```

---

## 🎓 Треки обучения

### 🟢 Трек "Пользователь" (30 мин)

→ Для тех, кто хочет использовать Helix

```
START_HERE.md
    ↓
guides/QUICKSTART.md
    ↓
QUICK_MODEL_SETUP.md
    ↓
helix chat-command ✨
```

---

### 🟡 Трек "Эксперт" (2 часа)

→ Для тех, кто хочет всё настроить

```
guides/QUICKSTART.md
    ↓
guides/CLI_GUIDE.md
    ↓
setup/MODELS_SETUP.md
    ↓
reference/IMPROVEMENTS.md
    ↓
Освоены все функции ✨
```

---

### 🔴 Трек "Разработчик" (4 часа)

→ Для тех, кто хочет расширить Helix

```
reference/SUMMARY.md
    ↓
reference/CLI_SUMMARY.md
    ↓
Изучение core/
    ↓
Изучение cli/
    ↓
Изучение api/
    ↓
Создание своих tools/skills ✨
```

---

## 💡 Советы

### Как быстро найти нужное?

1. **Начните с [README.md](README.md)** - общий обзор
2. **Используйте [INDEX.md](INDEX.md)** - алфавитный поиск
3. **Этот файл** - навигация по задачам

### Как учиться эффективно?

1. **Не читайте всё подряд** - выберите трек
2. **Практикуйтесь сразу** - запускайте команды
3. **Используйте примеры** - они есть во всех документах

### Куда идти дальше?

После освоения базы:
- Изучите [reference/IMPROVEMENTS.md](reference/IMPROVEMENTS.md) - узнаете о всех возможностях
- Создайте свой навык - практика лучший учитель
- Настройте профили для разных задач

---

## 📞 Помощь

### Не нашли ответ?

1. **Проверьте [TROUBLESHOOTING.md](TROUBLESHOOTING.md)**
2. **Поищите в [INDEX.md](INDEX.md)**
3. **Задайте вопрос в GitHub Issues**

### Хотите улучшить документацию?

1. Fork репозиторий
2. Внесите изменения в `docs/`
3. Создайте Pull Request

---

**Хорошего изучения Helix!** 🚀

---

**Обновлено:** 2025-06-01
**Версия:** 1.0
