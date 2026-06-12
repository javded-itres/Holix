# Telegram

**Telegram-канал:** [t.me/holix_agent](https://t.me/holix_agent) — новости и обновления проекта (это не бот, который вы настраиваете ниже).

У каждого профиля может быть свой бот. Секреты хранятся в:

`~/.holix/profiles/<имя>/telegram.env`

```bash
uv sync --extra telegram
holix -p shared telegram setup    # мастер: только токен бота
holix -p shared gateway start -f  # gateway + Telegram-бот
```

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

Подробно: [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

---

## Несколько ботов (полная изоляция)

Разные люди → разные профили → разные боты:

```bash
holix -p alice telegram setup
holix -p bob telegram setup
holix -p alice gateway start
holix -p bob gateway start
```

## Привязка user id → профиль (вручную)

```bash
holix -p shared telegram map set 123456789 alice
holix -p shared telegram map bind bob --user-id 987654321
holix -p shared telegram map list
```

Файлы: `profiles/shared/telegram-users.json`, опционально `HOLIX_TELEGRAM_USER_PROFILES` в `telegram.env`.  
Пользователь попадает в профиль автоматически; ручной `/profile` отключает автопривязку для чата.

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

После изменения `.env` или настроек голоса:

```bash
holix gateway reload
```