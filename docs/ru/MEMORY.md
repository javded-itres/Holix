# Память

Holix хранит историю диалогов и долгосрочные знания **на профиль**: **SQLite** + **ChromaDB** для семантического поиска.

Путь: `~/.holix/profiles/<имя>/data/memory/` (шифруется при [шифровании профиля](PROFILE_ENCRYPTION.md)).

---

## Что хранится

| Слой | Назначение |
|------|------------|
| Диалог | Сообщения по `conversation_id` (TUI, Telegram, cron, API) |
| Эпизодическая / стратегическая | Сводки и факты из успешных запусков |
| Reflexion | Критики качества / retry (`metadata.type=reflexion` или `self_refinement`) |
| Семантика (Chroma) | Эмбеддинги для `/memory` и `holix memory search` |
| Индекс навыков | Поиск по skills (отдельно от чата) |
| LangGraph checkpoints | Тех. снимки state графа в `checkpoints.db` (не знания чата/LTM) |

Агент подтягивает контекст автоматически; можно искать явно.

### Reflexion и LTM

При включённом **self-refinement** (по умолчанию) каждый evaluate/retry может писать:

- **эпизодическую** память — score, areas, accept vs retry
- **стратегическую** (при retry) — короткие советы «когда quality low on X…»

См. [EXECUTION_MODES.md](EXECUTION_MODES.md).

### Автоочистка `checkpoints.db` по размеру

Каждый run графа может дописывать state в `data/memory/checkpoints.db`. Это **не** диалоги и **не** LTM — только LangGraph. Параллельные run в одном процессе делят одно SQLite-соединение. Графы субагентов пишут чекпоинты в память, чтобы не блокировать родительский `checkpoints.db`.

Если суммарный размер (`checkpoints.db` + WAL/SHM) превышает лимит, Holix **удаляет файл и создаёт пустой** при следующем открытии графа. По умолчанию:

| Параметр | Env | По умолчанию |
|----------|-----|--------------|
| Автоочистка | `HOLIX_CHECKPOINT_AUTO_PRUNE` | `true` |
| Лимит (МиБ) | `HOLIX_CHECKPOINT_MAX_MB` | `200` |

`HOLIX_CHECKPOINT_MAX_MB=0` — отключить. В `.env` профиля:

```bash
HOLIX_CHECKPOINT_MAX_MB=200
HOLIX_CHECKPOINT_AUTO_PRUNE=true
```

Вручную (агент не пишет в профиль): `rm -f ~/.holix/profiles/<имя>/data/memory/checkpoints.db*`. Полная очистка data: `holix clear`.

---

## Поиск в чате

```text
/memory как настроили LiteLLM
/memory-clear
```

[SLASH_COMMANDS.md](SLASH_COMMANDS.md).

---

## CLI

```bash
holix memory search "конфигурация nginx"
```

Полная очистка `data/` профиля: `holix clear` (разрушительно) — [CLI.md](CLI.md).

---

## Сжатие контекста

`/compress` в TUI/Telegram при переполнении окна модели — [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## По интерфейсам

| Интерфейс | conversation_id |
|-----------|-----------------|
| TUI | id сессии (`/switch`) |
| Telegram / MAX | Чат + профиль |
| `holix run -c` | Ваш id |
| Cron (лог) | `cron-<job-id>` (скрыт в Telegram / MAX) |
| Cron → Telegram / MAX | активная сессия чата |
| Cron → Studio | новая сессия `studio_cron-…` |
| Gateway API | От клиента или сервера |

---

## Шифрование

При `holix profile crypto enable` БД памяти шифруются. На gateway нужен `HOLIX_UNLOCK_KEY` — [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md).

---

## pgvector {#pgvector}

По умолчанию семантика — **Chroma на диске**. Два `PersistentClient` на один каталог роняют процесс; Holix держит **один клиент на путь** (диалог, LTM и субагенты в том же процессе).

Общее хранилище в Postgres (Studio / несколько процессов):

```bash
pip install 'Holix[pgvector]'
export HOLIX_VECTOR_BACKEND=pgvector
export HOLIX_VECTOR_DSN='postgresql://user:pass@host/db'   # или STUDIO_DATABASE_URL
```

Таблица `holix_vectors`, MiniLM 384-d. Субагенты используют тот же DSN, без временного Chroma. Без `HOLIX_VECTOR_BACKEND` остаётся Chroma.

Прод-мессенджеры (systemd на VDS) ставят PostgreSQL + `postgresql-XX-pgvector` при деплое и пишут эти переменные в `.env` профиля. `CREATE EXTENSION vector` выполняет суперпользователь `postgres`; роли Holix достаточно прав на таблицы. SQLite диалогов не трогаем; существующая Chroma на диске не мигрируется.

---

## Проблемы

| Симптом | Действие |
|---------|----------|
| Пустой `/memory` | Выполните задачи; проверьте профиль |
| Плохой поиск | Провайдер эмбеддингов; `holix doctor` |
| Память locked | `HOLIX_UNLOCK_KEY` |

---

## См. также

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [PROFILES.md](PROFILES.md)
- [CLI.md](CLI.md)
