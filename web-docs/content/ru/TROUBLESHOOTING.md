# Решение проблем

## Gateway не стартует

```bash
holix doctor
holix gateway status
holix logs -s gateway -n 50
```

## Нет вывода агента / тихие ошибки

```bash
holix logs -l error -n 100
holix logs -s agent -f
holix logs debug on
```

## Windows

- Терминал: `dir`, `type`, `where` вместо `ls`, `cat`; Unix-команды можно добавить через `holix profile whitelist add` или `HOLIX_TERMINAL_WHITELIST_EXTRA` в `.env` профиля
- Субагенты — режим async
- Данные: `%LOCALAPPDATA%\Holix` или `HOLIX_HOME`
- Опционально: `uv sync --extra windows`

## Ошибка Dishka / agent init

```bash
holix doctor --fix
```

## LLM недоступен

```bash
holix models setup
ollama serve
holix doctor
```

## Telegram access denied

1. Пользователь должен отправить **`/start`** (режим access requests).
2. Назначьте Telegram-админа (один раз): `holix -p shared telegram requests approve USER_ID --set-admin`.
3. Админ одобряет новых: `holix -p shared telegram requests list` → `telegram requests approve USER_ID -i` или `--create-profile NAME`.
4. Для личного бота задайте `HOLIX_TELEGRAM_ALLOWED_USERS` (числовой user id).
5. В production используйте **именованный** профиль (`-p shared`), не `default`.

## Меню Telegram видно до одобрения

Slash-команды скрыты до approve (или allowlist / `map`). После одобрения выполните `holix telegram sync-menu`, если клиент показывает старое глобальное меню.

См. [TELEGRAM.md](TELEGRAM.md).

## API 401

Заголовок `Authorization: Bearer <key>` или `X-API-Key`. Admin key — через `/admin/api-keys`.

## См. также

- [LOGS.md](LOGS.md) — файлы логов, фильтры, ротация, debug