# Telegram

**Telegram-канал:** [t.me/helix_agent](https://t.me/helix_agent) — новости и обновления проекта (это не бот, который вы настраиваете ниже).

У каждого профиля может быть свой бот. Секреты хранятся в:

`~/.holix/profiles/<имя>/telegram.env`

```bash
uv sync --extra telegram
holix -p shared telegram setup    # мастер: только токен бота
holix -p shared gateway start -f  # gateway + Telegram-бот
```

### Хранение и загрузка токена

- Токен бота храните в `profiles/<хост-бота>/telegram.env`. При [шифровании профиля](CONFIGURATION.md#шифрование-профиля-опционально) файл шифруется на диске.
- **Не** оставляйте пустой `TELEGRAM_BOT_TOKEN=` в `global/.env` — это мешает подставить реальный токен из `telegram.env`. В global ключ лучше не указывать; Holix возьмёт значение из профиля (в т.ч. расшифрованное при заданном `HOLIX_UNLOCK_KEY`).
- Gateway при старте вызывает `load_telegram_env_files()` после unlock профиля, чтобы зашифрованный токен был доступен до запуска бота.

### Production (`uv tool install`)

При глобальной установке через uv явно добавьте aiogram:

```bash
uv tool install ~/Holix --force --with aiogram --with pypdf
```

Без aiogram в логе будет `Telegram bot skipped: aiogram is not installed`, даже если токен настроен.

### Уведомление об удалении профиля

При удалении профиля администратором (`holix profile delete` или `DELETE /api/holix/profiles/{id}`) Holix **сначала** отправляет сообщение в Telegram всем пользователям, привязанным к профилю. `--skip-notify` или `?notify=false` отключают уведомление. См. [PROFILES.md](PROFILES.md#удаление-профиля).

## Один бот — много пользователей (рекомендуется)

Один токен Telegram обслуживает многих людей. **User id вручную вводить не нужно.**

### 1. Админ: подключение бота

```bash
holix -p shared telegram setup
HOLIX_ENV=production holix -p shared gateway start -f
```

Мастер сохраняет только **токен бота** и включает **режим запросов доступа** (`HOLIX_TELEGRAM_ACCESS_REQUESTS=true` по умолчанию).

### 2. Первый администратор (только CLI)

Первого одобренного пользователя можно назначить **единственным** Telegram-администратором. Из Telegram это сделать нельзя — только через CLI:

```bash
holix -p shared telegram requests approve USER_ID --set-admin
```

Holix:

- создаёт профиль Holix **`admin`** (если его нет) и привязывает пользователя
- сохраняет `HOLIX_TELEGRAM_ADMIN_USER_ID` в `telegram.env`
- включает меню команд для этого пользователя

Проверка и сброс:

```bash
holix -p shared telegram admin show
holix -p shared telegram admin clear   # перед назначением другого админа
```

### 3. Пользователь: запрос доступа

1. Открывает бота в Telegram.
2. Отправляет `/start`.
3. Бот отвечает, что доступ ожидает одобрения (меню команд скрыто до approve).
4. Telegram-администратор получает **уведомление в Telegram** с командами CLI для одобрения или отклонения.

### 4. Админ: одобрение и изолированный профиль

```bash
holix -p shared telegram requests list
holix -p shared telegram requests approve USER_ID -i              # выбор или создание профиля
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

При одобрении Holix:

- создаёт **защищённый** профиль `ivan` с ключом `hp_…`
- включает **workspace jail** в `~/.holix/profiles/ivan/workspace/`
- привязывает Telegram-пользователя к профилю
- **отправляет ключ доступа пользователю в Telegram** (показывается один раз)

Пользователь сразу может писать боту — перезапуск не нужен.

> **Пути в ответах бота:** одобренные пользователи с workspace jail видят **только относительные пути** (`docs/report.pdf`, а не `~/.holix/profiles/ivan/workspace/…`). **Админ Telegram** (`HOLIX_TELEGRAM_ADMIN_USER_ID`) по-прежнему видит полные абсолютные пути. Подробнее: [Видимость путей в ответах](PROFILES.md#видимость-путей-в-ответах).

Другие команды:

```bash
holix -p shared telegram requests approve USER_ID --profile existing   # существующий открытый профиль
holix -p shared telegram requests reject USER_ID
holix -p shared telegram status
holix -p shared telegram sync-menu   # обновить меню только для одобренных
```

### Видимость меню команд

Меню slash-команд **скрыто** для неавторизованных пользователей. После approve (или allowlist / `map`) Holix включает меню **для каждого приватного чата**. `holix telegram sync-menu` обновляет меню всех авторизованных пользователей без перезапуска бота.

### Production

- Используйте **именованный профиль бота** (`-p shared`), не `default` — профиль `default` доступен **только в dev** при `HOLIX_ENV=production`.
- Для изоляции лучше `--create-profile` на каждого пользователя.
- Ручной allowlist (`HOLIX_TELEGRAM_ALLOWED_USERS`) не обязателен при включённых access requests.
- Telegram-администратор **только один** (`HOLIX_TELEGRAM_ADMIN_USER_ID`); назначение — `requests approve --set-admin`.

---

## Топологии с несколькими профилями

Каждый **профиль** — свой `.env`, `telegram.env`, gateway, память, cron в `~/.holix/profiles/<имя>/`. См. [PROFILES.md](PROFILES.md).

**Правило:** один токен бота = один polling-процесс. Два изолированных бота на **одном** токене невозможны.

| Подход | Изоляция | Настройка |
|--------|----------|-----------|
| **Один бот на профиль** | Полная | Отдельный токен @BotFather + gateway на профиль |
| **Один бот + access requests** | Профиль и jail на пользователя | § Один бот — много пользователей выше |
| **Один бот + `map` / `/profile`** | После ручной привязки | § Ручная привязка ниже |

### Один бот на профиль

```bash
holix -p alice telegram setup
holix -p bob telegram setup
# разные HOLIX_GATEWAY_PORT в .env каждого профиля
holix -p alice gateway start
holix -p bob gateway start
```

### Ручная привязка user → профиль

```bash
holix -p shared telegram map set 123456789 alice
holix -p shared telegram map bind bob --user-id 987654321
holix -p shared telegram map import "111:alice,222:bob"
holix -p shared telegram map list
```

- Файл: `profiles/<host>/telegram-users.json`
- Env: `HOLIX_TELEGRAM_USER_PROFILES` в `telegram.env`

Ручной `/profile` отключает автопривязку для чата.

### Типичные ошибки

- Один токен в нескольких `telegram.env` — работает только один poller.
- Одинаковый `HOLIX_GATEWAY_PORT` — второй gateway не стартует.
- Production без access requests / allowlist / `map`.

Одно live-сообщение на задачу; slash-команды как в TUI; inline-подтверждения.

---

## 🎙️ Голосовые сообщения

Holix умеет распознавать голосовые сообщения из Telegram и обрабатывать их как текст.

### Как это работает

1. Пользователь отправляет голосовое сообщение в Telegram
2. Бот скачивает аудиофайл
3. Отправляет его в OpenAI Whisper API для транскрибации
4. Показывает распознанный текст
5. Обрабатывает его через агента Holix как обычное текстовое сообщение

### Настройка

#### Вариант 1: LiteLLM (рекомендуется, если chat уже через LiteLLM)

На сервере LiteLLM добавьте модель транскрибации в `config.yaml`:

```yaml
model_list:
  - model_name: whisper          # имя для API
    litellm_params:
      model: whisper-1           # или groq/whisper-large-v3, azure/...
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      mode: audio_transcription
```

В `.env` Holix:

```bash
HOLIX_WHISPER_BASE_URL=http://192.168.88.252:4000/v1
HOLIX_WHISPER_API_KEY=sk-...     # virtual key LiteLLM
HOLIX_WHISPER_MODEL=whisper      # model_name из LiteLLM, не whisper-1
HOLIX_TELEGRAM_VOICE_LANGUAGE=ru
```

Или автоматически из профиля `litellm` (тот же ключ/URL, что для chat):

```bash
HOLIX_WHISPER_USE_PROFILE_LITELLM=true
HOLIX_WHISPER_MODEL=whisper
```

#### Вариант 2: Локально на машине с агентом (offline)

```bash
uv sync --extra telegram --extra voice
# ffmpeg должен быть в PATH

HOLIX_WHISPER_BACKEND=local
HOLIX_WHISPER_LOCAL_MODEL=base
HOLIX_TELEGRAM_VOICE_LANGUAGE=ru
```

**Ollama** не подходит для Whisper-транскрибации.

#### Вариант 3: OpenAI напрямую

```bash
OPENAI_API_KEY=sk-...
HOLIX_WHISPER_MODEL=whisper-1
```

### Использование

Отправьте голосовое сообщение или аудиофайл — Holix распознает текст и ответит как на обычное сообщение.

## Периодические задачи (cron)

Нужен запущенный gateway (`holix gateway start`). Управление: `/cron` (inline-меню) или `holix cron list`.

**Автосоздание (0.1.16+):** напишите повторяющийся запрос обычным языком, например:

- `Присылай новости каждый день в 10 утра`
- `Send me a disk usage summary every Monday at 9`

Holix создаст задачу и ответит id и временем следующего запуска. Результаты могут приходить в тот же чат Telegram. Подробнее: [CRON.md](CRON.md).

`/stop` останавливает агента, субагентов и ожидающие подтверждения, не удаляя cron-задачи.

После изменения `.env` или настроек голоса:

```bash
holix gateway reload
```