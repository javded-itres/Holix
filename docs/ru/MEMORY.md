# Память

Holix хранит историю диалогов и долгосрочные знания **на профиль**: **SQLite** + **ChromaDB** для семантического поиска.

Путь: `~/.holix/profiles/<имя>/data/memory/` (шифруется при [шифровании профиля](PROFILE_ENCRYPTION.md)).

---

## Что хранится

| Слой | Назначение |
|------|------------|
| Диалог | Сообщения по `conversation_id` (TUI, Telegram, cron, API) |
| Эпизодическая / стратегическая | Сводки и факты из успешных запусков |
| Семантика (Chroma) | Эмбеддинги для `/memory` и `holix memory search` |
| Индекс навыков | Поиск по skills (отдельно от чата) |

Агент подтягивает контекст автоматически; можно искать явно.

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
| Cron | `cron-<job-id>` |
| Gateway API | От клиента или сервера |

---

## Шифрование

При `holix profile crypto enable` БД памяти шифруются. На gateway нужен `HOLIX_UNLOCK_KEY` — [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md).

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