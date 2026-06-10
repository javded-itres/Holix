# Telegram

**Telegram-канал:** [t.me/helix_agent](https://t.me/helix_agent) — новости и обновления проекта (это не бот, который вы настраиваете ниже).

У каждого профиля может быть свой бот. Секреты хранятся в:

`~/.helix/profiles/<имя>/telegram.env`

```bash
uv sync --extra telegram
helix -p shared telegram setup    # мастер: только токен бота
helix -p shared gateway start -f  # gateway + Telegram-бот
```

## Один бот — много пользователей (рекомендуется)

Один токен Telegram обслуживает многих людей. **User id вручную вводить не нужно.**

### 1. Админ: подключение бота

```bash
helix -p shared telegram setup
HELIX_ENV=production helix -p shared gateway start -f
```

Мастер сохраняет только **токен бота** и включает **режим запросов доступа** (`HELIX_TELEGRAM_ACCESS_REQUESTS=true` по умолчанию).

### 2. Первый администратор (только CLI)

Первого одобренного пользователя можно назначить **единственным** Telegram-администратором. Из Telegram это сделать нельзя — только через CLI:

```bash
helix -p shared telegram requests approve USER_ID --set-admin
```

Helix:

- создаёт профиль Helix **`admin`** (если его нет) и привязывает пользователя
- сохраняет `HELIX_TELEGRAM_ADMIN_USER_ID` в `telegram.env`
- включает меню команд для этого пользователя

Проверка и сброс:

```bash
helix -p shared telegram admin show
helix -p shared telegram admin clear   # перед назначением другого админа
```

### 3. Пользователь: запрос доступа

1. Открывает бота в Telegram.
2. Отправляет `/start`.
3. Бот отвечает, что доступ ожидает одобрения (меню команд скрыто до approve).
4. Telegram-администратор получает **уведомление в Telegram** с командами CLI для одобрения или отклонения.

### 4. Админ: одобрение и изолированный профиль

```bash
helix -p shared telegram requests list
helix -p shared telegram requests approve USER_ID -i              # выбор или создание профиля
helix -p shared telegram requests approve USER_ID --create-profile ivan
```

При одобрении Helix:

- создаёт **защищённый** профиль `ivan` с ключом `hp_…`
- включает **workspace jail** в `~/.helix/profiles/ivan/workspace/`
- привязывает Telegram-пользователя к профилю
- **отправляет ключ доступа пользователю в Telegram** (показывается один раз)

Пользователь сразу может писать боту — перезапуск не нужен.

Другие команды:

```bash
helix -p shared telegram requests approve USER_ID --profile existing   # существующий открытый профиль
helix -p shared telegram requests reject USER_ID
helix -p shared telegram status
helix -p shared telegram sync-menu   # обновить меню только для одобренных
```

### Видимость меню команд

Меню slash-команд **скрыто** для неавторизованных пользователей. После approve (или allowlist / `map`) Helix включает меню **для каждого приватного чата**. `helix telegram sync-menu` обновляет меню всех авторизованных пользователей без перезапуска бота.

### Production

- Используйте **именованный профиль бота** (`-p shared`), не `default` — профиль `default` доступен **только в dev** при `HELIX_ENV=production`.
- Для изоляции лучше `--create-profile` на каждого пользователя.
- Ручной allowlist (`HELIX_TELEGRAM_ALLOWED_USERS`) не обязателен при включённых access requests.
- Telegram-администратор **только один** (`HELIX_TELEGRAM_ADMIN_USER_ID`); назначение — `requests approve --set-admin`.

Подробно: [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

---

## Несколько ботов (полная изоляция)

Разные люди → разные профили → разные боты:

```bash
helix -p alice telegram setup
helix -p bob telegram setup
helix -p alice gateway start
helix -p bob gateway start
```

## Привязка user id → профиль (вручную)

```bash
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map bind bob --user-id 987654321
helix -p shared telegram map list
```

Файлы: `profiles/shared/telegram-users.json`, опционально `HELIX_TELEGRAM_USER_PROFILES` в `telegram.env`.  
Пользователь попадает в профиль автоматически; ручной `/profile` отключает автопривязку для чата.

Одно live-сообщение на задачу; slash-команды как в TUI; inline-подтверждения.

---

## 🎙️ Голосовые сообщения

Helix умеет распознавать голосовые сообщения из Telegram и обрабатывать их как текст.

### Как это работает

1. Пользователь отправляет голосовое сообщение в Telegram
2. Бот скачивает аудиофайл
3. Отправляет его в OpenAI Whisper API для транскрибации
4. Показывает распознанный текст
5. Обрабатывает его через агента Helix как обычное текстовое сообщение

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

В `.env` Helix:

```bash
HELIX_WHISPER_BASE_URL=http://192.168.88.252:4000/v1
HELIX_WHISPER_API_KEY=sk-...     # virtual key LiteLLM
HELIX_WHISPER_MODEL=whisper      # model_name из LiteLLM, не whisper-1
HELIX_TELEGRAM_VOICE_LANGUAGE=ru
```

Или автоматически из профиля `litellm` (тот же ключ/URL, что для chat):

```bash
HELIX_WHISPER_USE_PROFILE_LITELLM=true
HELIX_WHISPER_MODEL=whisper
```

#### Вариант 2: Локально на машине с агентом (offline)

```bash
uv sync --extra telegram --extra voice
# ffmpeg должен быть в PATH

HELIX_WHISPER_BACKEND=local
HELIX_WHISPER_LOCAL_MODEL=base
HELIX_TELEGRAM_VOICE_LANGUAGE=ru
```

**Ollama** не подходит для Whisper-транскрибации.

#### Вариант 3: OpenAI напрямую

```bash
OPENAI_API_KEY=sk-...
HELIX_WHISPER_MODEL=whisper-1
```

### Использование

Отправьте голосовое сообщение или аудиофайл — Helix распознает текст и ответит как на обычное сообщение.

После изменения `.env` или настроек голоса:

```bash
helix gateway reload
```