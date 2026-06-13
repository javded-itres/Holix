# MAX — мессенджер

Holix интегрируется с [MAX](https://max.ru) — российской платформой мессенджера — чтобы запускать того же самообучающегося агента в личных и групповых чатах.

Официальная документация API: [dev.max.ru/docs-api](https://dev.max.ru/docs-api)

У каждого **host-профиля** бота может быть свой токен. Секреты хранятся в:

`~/.holix/profiles/<имя>/max.env`

```bash
uv sync --extra max
holix -p shared max setup          # мастер: токен, режим, allowlist
holix -p shared gateway start -f   # gateway + MAX webhook (продакшен)
```

В production (`HELIX_ENV=production`) нужен allowlist или режим запросов доступа.

### Хранение и загрузка токена

- Токен бота храните в `profiles/<host-бота>/max.env`. При [шифровании профиля](CONFIGURATION.md#шифрование-профиля-опционально) файл шифруется на диске (через общий `integrations/messenger/env_store`, как у Telegram).
- Канонические ключи — `HOLIX_MAX_*`; legacy `HELIX_MAX_*` поддерживаются при чтении и миграции.
- **Не** оставляйте пустой `MAX_ACCESS_TOKEN=` в `global/.env` — это мешает подставить реальный токен из `max.env`. В global ключ лучше не указывать; Holix возьмёт значение из профиля (в т.ч. расшифрованное при заданном `HOLIX_UNLOCK_KEY`).
- Gateway при старте вызывает `load_max_env_files()` после unlock профиля, чтобы зашифрованный токен был доступен до регистрации webhook.

### Production (`uv tool install`)

При глобальной установке через uv явно добавьте extra `max`:

```bash
uv tool install ~/Holix --force --with "Holix[max]"
```

Без зависимостей MAX в логе будет пропуск companion-процесса, даже если токен настроен.

## Один бот — много пользователей (рекомендуется)

Один токен MAX обслуживает многих людей. **User id вручную вводить не нужно.**

### 1. Админ: подключение бота

```bash
holix -p shared max setup
HOLIX_ENV=production holix -p shared gateway start -f
```

Мастер сохраняет **токен бота** и по умолчанию включает **режим запросов доступа** (`HOLIX_MAX_ACCESS_REQUESTS=true`).

Создайте бота в [business.max.ru](https://business.max.ru/self) → **Чат-боты** → **Интеграция**, скопируйте access token.

### 2. Первый администратор (только CLI)

Первого одобренного пользователя можно назначить **единственным** MAX-администратором. Из MAX это сделать нельзя — только через CLI:

```bash
holix -p shared max requests approve USER_ID --set-admin
```

Holix:

- создаёт профиль Holix **`admin`** (если его нет) и привязывает пользователя
- сохраняет `HOLIX_MAX_ADMIN_USER_ID` в `max.env`
- включает расширенные команды для этого пользователя (`/message`, `/init`, установка MCP)

Проверка и сброс:

```bash
holix -p shared max admin show
holix -p shared max admin clear   # перед назначением другого админа
```

### 3. Пользователь: запрос доступа

1. Открывает бота в MAX.
2. Отправляет `/start`.
3. Бот отвечает, что доступ ожидает одобрения.
4. MAX-администратор получает **уведомление в MAX** с командами CLI для одобрения или отклонения.

### 4. Админ: одобрение и изолированный профиль

```bash
holix -p shared max requests list
holix -p shared max requests approve USER_ID -i              # выбор или создание профиля
holix -p shared max requests approve USER_ID --create-profile ivan
```

При одобрении Holix:

- создаёт **защищённый** профиль `ivan` с ключом `hp_…`
- включает **workspace jail** в `~/.holix/profiles/ivan/workspace/`
- привязывает MAX-пользователя к профилю
- **отправляет ключ доступа пользователю в MAX** (показывается один раз)

Пользователь сразу может писать боту — перезапуск не нужен.

> **Пути в ответах бота:** одобренные пользователи с workspace jail видят **только относительные пути** (`docs/report.pdf`, а не `~/.holix/profiles/ivan/workspace/…`). **Админ MAX** (`HOLIX_MAX_ADMIN_USER_ID`) по-прежнему видит полные абсолютные пути. Подробнее: [Видимость путей в ответах](PROFILES.md#видимость-путей-в-ответах).

Другие команды:

```bash
holix -p shared max requests approve USER_ID --profile existing   # существующий открытый профиль
holix -p shared max requests reject USER_ID
holix -p shared max status
```

### Production

- Используйте **именованный host-профиль** (`-p shared`), не `default` — профиль `default` доступен **только в dev** при `HOLIX_ENV=production`.
- Для изоляции лучше `--create-profile` на каждого пользователя.
- Ручной allowlist (`HOLIX_MAX_ALLOWED_USERS`) не обязателен при включённых access requests.
- MAX-администратор **только один** (`HOLIX_MAX_ADMIN_USER_ID`); назначение — `requests approve --set-admin`.

Подробно: [MAX_MULTI_PROFILE.md](MAX_MULTI_PROFILE.md).

---

## Несколько ботов (полная изоляция)

Разные люди → разные профили → разные боты:

```bash
holix -p alice max setup
holix -p bob max setup
holix -p alice gateway start
holix -p bob gateway start
```

У каждого профиля свой `max.env`, свой webhook URL и порт gateway.

## Привязка user id → профиль (вручную)

```bash
holix -p shared max map set 123456789 alice
holix -p shared max map bind bob --user-id 987654321
holix -p shared max map list
```

Файлы: `profiles/shared/max-users.json`, опционально `HOLIX_MAX_USER_PROFILES` в `max.env`.

Одно live-сообщение на задачу; slash-команды как в TUI; inline-подтверждения опасных инструментов.

---

## Режимы доставки событий

MAX поддерживает **один** режим одновременно:

| Режим | Когда использовать | Команда Holix |
|-------|-------------------|---------------|
| **Webhook** | Продакшен | `holix gateway start` |
| **Long Polling** | Локальная разработка | `holix max` |

```bash
# Разработка (Long Polling — только dev/test):
holix max

# Продакшен (Webhook через gateway):
holix gateway start
```

Gateway регистрирует webhook в MAX (`POST /subscriptions`) и обслуживает `POST /max/webhook`.

Long Polling (`GET /updates`) ограничен по скорости и не подходит для продакшена. MAX рекомендует HTTPS webhook на порту 443 с доверенным TLS-сертификатом.

После смены `max.env` или привязок при работающем gateway:

```bash
holix gateway reload
```

## Переменные окружения

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `MAX_ACCESS_TOKEN` | Да | Токен бота с business.max.ru |
| `HOLIX_MAX_ALLOWED_USERS` | Prod* | Allowlist `user_id` через запятую |
| `HOLIX_MAX_ACCESS_REQUESTS` | Нет | Запросы доступа через `/start` (по умолчанию `true` в setup) |
| `HOLIX_MAX_ALLOW_ALL` | Нет | Разрешить всех (только dev) |
| `HOLIX_MAX_MODE` | Нет | `webhook` (prod) или `polling` (dev/test) |
| `HOLIX_MAX_WEBHOOK_URL` | Webhook | Публичный HTTPS URL для событий |
| `HOLIX_MAX_WEBHOOK_SECRET` | Webhook | Секрет для заголовка `X-Max-Bot-Api-Secret` |
| `HOLIX_MAX_ADMIN_USER_ID` | Нет | Единственный администратор MAX |
| `HOLIX_MAX_PROFILE` | Нет | Профиль Holix host-бота |

\* При `HOLIX_MAX_ACCESS_REQUESTS=true` ручной allowlist не обязателен.

Токен передаётся в заголовке `Authorization` — query-параметры **не** поддерживаются API MAX.

## Команды CLI

| Команда | Описание |
|---------|----------|
| `holix max setup` | Мастер: токен, allowlist, режим, `profiles/{p}/max.env` |
| `holix max` | Запуск бота (Long Polling — только dev/test) |
| `holix max status` | Токен, админ, карта пользователей, ожидающие заявки, подписки |
| `holix max map` | Привязки user → profile |
| `holix max requests` | Список/одобрение/отклонение заявок |
| `holix max admin` | Показать/сбросить администратора MAX |
| `holix gateway start` | Gateway + MAX webhook companion |
| `holix gateway status` | Health gateway + сводка MAX (env/admin/map) |

Management API: `GET /api/holix/profiles/{id}/max/status`, `…/requests`, `…/map`, `…/admin`.

См. [CLI.md](CLI.md#holix-max).

## Возможности

### Диалоги с агентом

- Одно live-сообщение на задачу (редактирование через `PUT /messages` при стриминге)
- ID сессии: `max_{profile}_{user_id}`
- Общие слэш-команды с TUI: `/help`, `/profile`, `/models`, `/new`, `/stop` — см. [SLASH_COMMANDS.md](SLASH_COMMANDS.md)

### Inline-подтверждения

Когда агент запрашивает подтверждение опасного инструмента, Holix отправляет inline-клавиатуру. Нажатие кнопки → событие `message_callback` → ответ через `POST /answers`.

### Файлы

Отправка и приём вложений через `POST /uploads`. Извлечение текста из файлов — общий пайплайн с Telegram. В чате доступен инструмент `send_chat_files`.

### Markdown в ответах

Форматирование ответов агента в markdown MAX (`**жирный**`, `*курсив*`, `` `код` ``, ссылки). Длинные ответы разбиваются на части.

## Архитектура

```
integrations/max/
├── client.py         # REST-клиент (platform-api.max.ru)
├── host.py           # multi-user host, ACL, routing
├── bot.py            # диспетчер событий
├── webhook.py        # FastAPI route POST /max/webhook
├── polling.py        # цикл GET /updates (dev)
├── env_store.py      # profiles/<p>/max.env (messenger/env_store)
└── main.py           # точка входа holix max
```

Паттерн повторяет `integrations/telegram/`, но использует лёгкий HTTP-клиент (`aiohttp`) вместо aiogram.

## Чеклист для продакшена

1. Публичный **HTTPS** endpoint на порту 443 (reverse proxy → gateway)
2. `HOLIX_MAX_MODE=webhook` и корректный `HOLIX_MAX_WEBHOOK_URL`
3. Allowlist или access requests; `HOLIX_ENV=production`
4. Лимит MAX: **30 rps** на `platform-api.max.ru`

См. [DEPLOYMENT.md](DEPLOYMENT.md) и [SECURITY.md](SECURITY.md).

## Решение проблем

| Симптом | Решение |
|---------|---------|
| `401` от MAX API | Проверьте `MAX_ACCESS_TOKEN`; перезапустите `holix max setup` |
| Нет событий webhook | Проверьте HTTPS URL, `POST /subscriptions`, логи gateway |
| Polling перестал работать после webhook | Активен только один режим — сначала удалите подписку webhook |
| Пользователь игнорируется | Одобрите через `holix max requests approve` или добавьте в allowlist |
| Агент не отправляет файлы | `uv sync --extra max`; в чате MAX доступен `send_chat_files` |
| Ошибки `429` | Снизьте частоту отправки; клиент Holix ограничивает ≤30 rps |

Запустите `holix doctor` для проверки токена, webhook и allowlist.

## См. также

- [MAX_MULTI_PROFILE.md](MAX_MULTI_PROFILE.md) — один бот / несколько ботов, изоляция
- [TELEGRAM.md](TELEGRAM.md) — параллельная интеграция с Telegram
- [GATEWAY.md](GATEWAY.md) — HTTP gateway и companions
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — команды `/` в чатах MAX