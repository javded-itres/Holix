# MAX — мессенджер

Holix интегрируется с [MAX](https://max.ru) — российской платформой мессенджера — чтобы запускать того же самообучающегося агента в личных и групповых чатах.

Официальная документация API: [dev.max.ru/docs-api](https://dev.max.ru/docs-api)

У каждого **host-профиля** бота может быть свой токен. Секреты хранятся в:

`~/.holix/profiles/<имя>/max.env`

```bash
uv sync --extra max
holix -p shared max setup          # мастер: токен, режим, allowlist
holix -p shared gateway start        # gateway + MAX (polling в dev, webhook в prod)
```

В production (`HELIX_ENV=production`) нужен allowlist или режим запросов доступа.

---

## Полная инструкция: регистрация бота и переменные

Пошаговое руководство: от создания бота в кабинете MAX до рабочего агента в чате.

### Что понадобится

| Требование | Зачем |
|------------|-------|
| Организация на [business.max.ru](https://business.max.ru/self) | Без неё нельзя выпустить токен бота |
| Установленный Holix с extra `max` | HTTP-клиент, polling, webhook |
| Профиль Holix для host-бота | Обычно `shared` или `admin` — не `default` в production |
| LLM настроен в профиле | `holix models setup` или ключи в `profiles/<имя>/.env` |

Файл с секретами MAX:

`~/.holix/profiles/<host-профиль>/max.env`

Пример для host-профиля `shared`: `~/.holix/profiles/shared/max.env`.

### Шаг 1. Создать бота в кабинете MAX

1. Откройте [business.max.ru/self](https://business.max.ru/self) и войдите под учётной записью организации.
2. Перейдите в раздел **Чат-боты** (или **Боты** / **Интеграция** — название может отличаться в интерфейсе).
3. Нажмите **Создать бота** / **Добавить бота**.
4. Заполните карточку бота:
   - **Имя** — как бот отображается пользователям в MAX.
   - **Описание** — кратко, для чего бот (по желанию).
   - **Аватар** — по желанию.
5. Откройте вкладку **Интеграция** (или **API** / **Токен доступа**).
6. Скопируйте **Access token** (токен доступа бота).  
   Это длинная строка; храните как пароль — не публикуйте в git и чатах.
7. Убедитесь, что бот **опубликован** / **включён** (если в кабинете есть переключатель активности).

Официальная документация API: [dev.max.ru/docs-api](https://dev.max.ru/docs-api).

> **Важно:** токен передаётся в заголовке `Authorization` при запросах к `platform-api.max.ru`. Query-параметры с токеном API не принимает.

### Шаг 2. Узнать свой MAX user id

User id — числовой идентификатор пользователя в MAX. Нужен для allowlist и назначения администратора.

**Способ A — через мастер Holix (рекомендуется):**

```bash
holix -p shared max setup
```

На шаге «Ваш MAX user id» выберите автоопределение: напишите боту любое сообщение в MAX — Holix поймает событие и подставит id.

**Способ B — вручную:**

- Посмотрите id в уведомлении после `/start`, если бот уже запущен с access requests.
- Или одобрите заявку через `holix max requests list` — в списке будет `user_id`.

Формат в конфиге: одно число или несколько через запятую: `123456789` или `111,222,333`.

### Шаг 3. Установить зависимости и запустить мастер

```bash
# из каталога репозитория Holix
uv sync --extra max

# глобальная установка (production)
uv tool install ~/Holix --force --with "Holix[max]"
```

Интерактивная настройка:

```bash
holix -p shared max setup
```

Мастер по шагам:

1. Проверяет токен (`GET /me` к MAX API).
2. Спрашивает allowlist (ваш user id) или определяет его автоматически.
3. Выбирает профиль Holix host-бота (`HOLIX_MAX_PROFILE`).
4. Выбирает режим: `polling` (разработка) или `webhook` (продакшен).
5. Для webhook — запрашивает публичный HTTPS URL и секрет.
6. Сохраняет всё в `~/.holix/profiles/shared/max.env`.
7. По умолчанию включает **запросы доступа** (`HOLIX_MAX_ACCESS_REQUESTS=true`).

Проверка после настройки:

```bash
holix -p shared max status
holix doctor
```

### Шаг 4. Запуск бота

| Окружение | `HOLIX_MAX_MODE` | Команда |
|-----------|------------------|---------|
| Разработка (`HOLIX_ENV` ≠ `production`) | `polling` (по умолчанию) | `holix -p shared gateway start` |
| Продакшен | `webhook` (принудительно) | `holix -p shared gateway start -f` |

В **development** gateway сам поднимает MAX Long Polling — отдельно `holix max` не обязателен.

В **production** нужны публичный HTTPS и `HOLIX_MAX_WEBHOOK_URL` (см. пример ниже).

```bash
# локальная разработка
holix -p shared gateway start

# продакшен (именованный профиль + production)
HOLIX_ENV=production holix -p shared gateway start -f
```

Проверка:

```bash
holix -p shared gateway status
```

### Шаг 5. Ручное заполнение `max.env`

Если мастер не подходит, создайте или отредактируйте файл вручную.

**Разработка (polling, запросы доступа):**

```env
# ~/.holix/profiles/shared/max.env
# Holix MAX — generated manually

MAX_ACCESS_TOKEN=ваш_токен_из_business_max_ru

# Режим доставки: polling в dev (gateway поднимет companion)
HOLIX_MAX_MODE=polling

# Профиль Holix, в котором живёт host-бот (токен, карта пользователей)
HOLIX_MAX_PROFILE=shared

# Новые пользователи подают заявку через /start (рекомендуется)
HOLIX_MAX_ACCESS_REQUESTS=true

# Ваш user id (опционально при access requests — можно одобрять через CLI)
HOLIX_MAX_ALLOWED_USERS=123456789

# Только для локальных тестов без заявок (НЕ в production):
# HOLIX_MAX_ALLOW_ALL=true
```

**Продакшен (webhook):**

```env
# ~/.holix/profiles/shared/max.env

MAX_ACCESS_TOKEN=ваш_токен_из_business_max_ru

HOLIX_MAX_MODE=webhook
HOLIX_MAX_PROFILE=shared
HOLIX_MAX_ACCESS_REQUESTS=true

# Публичный URL, куда MAX шлёт события (HTTPS, порт 443)
# Обычно: https://ваш-домен/max/webhook
HOLIX_MAX_WEBHOOK_URL=https://agent.example.com/max/webhook

# Секрет для заголовка X-Max-Bot-Api-Secret (придумайте длинную случайную строку)
HOLIX_MAX_WEBHOOK_SECRET=случайная_строка_32_символа_и_больше

# Администратор назначается CLI, но можно оставить пустым до первого approve --set-admin
# HOLIX_MAX_ADMIN_USER_ID=123456789
# HOLIX_MAX_ADMIN_PROFILE=admin
```

После правки `max.env` при работающем gateway:

```bash
holix -p shared gateway reload
```

### Справочник переменных (полный)

| Переменная | Обязательно | Пример | Описание |
|------------|-------------|--------|----------|
| `MAX_ACCESS_TOKEN` | **Да** | `AbCdEf…` | Токен бота из business.max.ru → Интеграция. Канонический ключ; legacy: `HOLIX_MAX_ACCESS_TOKEN`. |
| `HOLIX_MAX_PROFILE` | Нет | `shared` | Профиль Holix host-бота (где лежит `max.env`, карта пользователей). По умолчанию — активный `-p` профиль. |
| `HOLIX_MAX_MODE` | Нет | `polling` / `webhook` | Режим доставки. В `HOLIX_ENV=production` всегда принудительно `webhook`. |
| `HOLIX_MAX_WEBHOOK_URL` | Webhook | `https://host/max/webhook` | Публичный HTTPS endpoint Holix gateway (`POST /max/webhook`). |
| `HOLIX_MAX_WEBHOOK_SECRET` | Webhook* | `my-secret-…` | Секрет в заголовке `X-Max-Bot-Api-Secret`. Рекомендуется в production. |
| `HOLIX_MAX_ACCESS_REQUESTS` | Нет | `true` | Режим заявок: пользователь пишет `/start`, админ одобряет через CLI. По умолчанию `true` в `max setup`. |
| `HOLIX_MAX_ALLOWED_USERS` | Prod** | `123,456` | Allowlist: только эти `user_id` могут пользоваться ботом (если нет access requests). |
| `HOLIX_MAX_ALLOW_ALL` | Нет | `true` | Пропускать всех без проверки. **Только dev.** |
| `HOLIX_MAX_ADMIN_USER_ID` | Нет | `123456789` | Единственный администратор MAX. Назначается: `max requests approve ID --set-admin`. |
| `HOLIX_MAX_ADMIN_PROFILE` | Нет | `admin` | Профиль Holix администратора (обычно `admin`). |
| `HOLIX_MAX_USER_PROFILES` | Нет | `111:alice,222:bob` | Статическая карта `user_id` → профиль (альтернатива `max-users.json`). |
| `HOLIX_MAX_POLL_TIMEOUT` | Нет | `5` | Таймаут long poll в секундах (0–90). |
| `HOLIX_MAX_EDIT_INTERVAL_MS` | Нет | `1500` | Интервал обновления live-сообщения (мс). |
| `HOLIX_MAX_HEARTBEAT_INTERVAL` | Нет | `45` | Интервал heartbeat при долгих задачах (с). |

\* Без секрета webhook может работать, но в production лучше задать.  
\*\* При `HOLIX_MAX_ACCESS_REQUESTS=true` ручной allowlist не обязателен.

**Связанные файлы (не в `max.env`):**

| Файл | Назначение |
|------|------------|
| `profiles/<host>/max-users.json` | Привязки MAX user id → профиль Holix |
| `profiles/<host>/max-access-requests.json` | Очередь заявок на доступ |
| `profiles/<host>/.env` | LLM, gateway, шифрование — отдельно от токена бота |

**Чего не делать:**

- Не кладите пустой `MAX_ACCESS_TOKEN=` в `global/.env` — он перекроет реальный токен из `max.env`.
- Не используйте `HOLIX_MAX_ALLOW_ALL=true` в production.
- Не храните токен в git; при шифровании профиля `max.env` шифруется на диске автоматически.

### Типичные ошибки при заполнении

| Ошибка | Решение |
|--------|---------|
| `401` от MAX API | Проверьте токен; пересоздайте в кабинете; `holix max setup` |
| Бот не отвечает в dev | Запустите `holix gateway start`; проверьте `holix max status` → Mode: polling |
| Webhook не приходит | HTTPS на 443, корректный URL, `holix gateway status`, логи gateway |
| «Access denied» | Одобрите `holix max requests approve` или добавьте id в allowlist |
| Два режима сразу | Активен только polling **или** webhook — удалите webhook-подписку перед polling |

---

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

| Режим | Когда использовать | Как запускается в Holix |
|-------|-------------------|-------------------------|
| **Webhook** | Продакшен (`HOLIX_ENV=production`) | `holix gateway start` — регистрация в gateway |
| **Long Polling** | Локальная разработка | `holix gateway start` — companion polling в gateway |

```bash
# Разработка (polling через gateway — рекомендуется):
holix -p shared gateway start

# Альтернатива: только бот без API gateway
holix -p shared max

# Продакшен (webhook через gateway):
HOLIX_ENV=production holix -p shared gateway start -f
```

В development gateway **сам** поднимает MAX Long Polling (как companion Telegram). Отдельный процесс `holix max` нужен только если API gateway не запущен.

В production gateway регистрирует webhook в MAX (`POST /subscriptions`) и обслуживает `POST /max/webhook`.

Long Polling (`GET /updates`) ограничен по скорости и не подходит для продакшена. MAX рекомендует HTTPS webhook на порту 443 с доверенным TLS-сертификатом.

После смены `max.env` или привязок при работающем gateway:

```bash
holix gateway reload
```

## Переменные окружения

Краткая таблица. Полный справочник с примерами — в разделе [Полная инструкция](#полная-инструкция-регистрация-бота-и-переменные) выше.

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `MAX_ACCESS_TOKEN` | Да | Токен бота с business.max.ru |
| `HOLIX_MAX_PROFILE` | Нет | Профиль Holix host-бота |
| `HOLIX_MAX_MODE` | Нет | `polling` (dev) или `webhook` (prod) |
| `HOLIX_MAX_WEBHOOK_URL` | Webhook | Публичный HTTPS URL (`/max/webhook`) |
| `HOLIX_MAX_WEBHOOK_SECRET` | Webhook | Секрет `X-Max-Bot-Api-Secret` |
| `HOLIX_MAX_ACCESS_REQUESTS` | Нет | Заявки через `/start` (по умолчанию `true`) |
| `HOLIX_MAX_ALLOWED_USERS` | Prod* | Allowlist `user_id` через запятую |
| `HOLIX_MAX_ALLOW_ALL` | Нет | Разрешить всех (только dev) |
| `HOLIX_MAX_ADMIN_USER_ID` | Нет | Единственный администратор MAX |
| `HOLIX_MAX_ADMIN_PROFILE` | Нет | Профиль Holix админа (обычно `admin`) |
| `HOLIX_MAX_USER_PROFILES` | Нет | Карта `user_id:profile` в одной строке |

\* При `HOLIX_MAX_ACCESS_REQUESTS=true` ручной allowlist не обязателен.

Токен передаётся в заголовке `Authorization` — query-параметры **не** поддерживаются API MAX.

## Команды CLI

| Команда | Описание |
|---------|----------|
| `holix max setup` | Мастер: токен, allowlist, режим, `profiles/{p}/max.env` |
| `holix max` | Только бот (polling), без API gateway |
| `holix max status` | Токен, админ, карта пользователей, ожидающие заявки, подписки |
| `holix max map` | Привязки user → profile |
| `holix max requests` | Список/одобрение/отклонение заявок |
| `holix max admin` | Показать/сбросить администратора MAX |
| `holix gateway start` | Gateway + MAX (polling в dev, webhook в prod) |
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