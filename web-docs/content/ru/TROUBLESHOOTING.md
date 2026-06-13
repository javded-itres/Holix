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

## Telegram-бот не стартует вместе с gateway

В логе: `Telegram bot skipped` или `telegram (disabled)` в списке companions.

| Сообщение | Решение |
|-----------|---------|
| `set TELEGRAM_BOT_TOKEN` / токен не настроен | Уберите пустой `TELEGRAM_BOT_TOKEN=` из `global/.env`; храните токен в `profiles/<имя>/telegram.env`. Задайте `HOLIX_UNLOCK_KEY`, если файл зашифрован. Перезапустите gateway. |
| `aiogram is not installed` | `uv sync --extra telegram` (из исходников) или `uv tool install . --force --with aiogram --with pypdf` (глобальный tool). Перезапуск gateway. |
| Токен есть, бот всё равно выключен | `holix -p NAME telegram status` — маскированный токен. Проверьте `profiles/NAME/gateway/gateway.log` после перезапуска. |

```bash
holix -p shared telegram status
holix -p shared gateway reload
```

## API 401

Заголовок `Authorization: Bearer <key>` или `X-API-Key`. Admin key — через `/admin/api-keys`.

## Пути workspace: `[restricted]` или только относительные

**Ожидаемое поведение**, если включён [workspace jail](PROFILES.md#workspace-jail-изоляция-в-директории) и вызывающий **не** администратор:

- В ответах агента и выводе инструментов пути вида `docs/file.txt` или `.` (корень jail), а не `/home/…/.holix/profiles/…`.
- Пути вне jail отображаются как `[restricted]`.

Это **не баг**, если пользователь Telegram или API-клиент без `admin` не видит абсолютные пути хоста.

Чтобы видеть полные пути:

| Интерфейс | Требование |
|-----------|------------|
| Telegram | Ваш numeric user id совпадает с `HOLIX_TELEGRAM_ADMIN_USER_ID` (назначение: `telegram requests approve … --set-admin`) |
| Gateway API | В `permissions` API-ключа есть `admin` (`POST /admin/api-keys`) |
| Локальный CLI на сервере | Сессия без jail или jail отключён для профиля |

Проверка jail: `holix -p NAME profile jail status`. Подробнее: [Видимость путей в ответах](PROFILES.md#видимость-путей-в-ответах).

## Админ в Telegram всё ещё видит относительные пути

1. Проверьте назначение: `holix -p shared telegram admin show` — должен быть ваш Telegram user id.
2. Переназначьте при необходимости: `holix -p shared telegram requests approve USER_ID --set-admin` (только CLI).
3. Полные пути получает только **один** сохранённый админ; остальные одобренные пользователи — относительные.

## Админ через API всё ещё видит относительные пути

1. Проверьте права ключа: `GET /admin/api-keys` (нужен admin key) — в `permissions` должно быть `"admin"`.
2. Пересоздайте ключ с admin:
   ```bash
   curl -sS -X POST "$HOLIX_URL/admin/api-keys" \
     -H "Authorization: Bearer $ADMIN_KEY" \
     -d "name=ops-admin&permissions=read,write,execute,admin&rate_limit=1000"
   ```
3. У профиля должен быть `workspace_jail_enabled: true`; без jail все видят полные пути.

## См. также

- [LOGS.md](LOGS.md) — файлы логов, фильтры, ротация, debug