# Telegram

У каждого профиля свой бот и allowlist. Секреты хранятся в:

`~/.helix/profiles/<имя>/telegram.env`

```bash
uv sync --extra telegram
helix telegram setup    # мастер: токен, allowlist, сохранение в профиль
helix telegram run
# или вместе с gateway того же профиля:
helix gateway start
```

В production (`HELIX_ENV=production`) обязателен `HELIX_TELEGRAM_ALLOWED_USERS`.

Разные люди → разные профили → разные боты:

```bash
helix -p alice telegram setup
helix -p bob telegram setup
```

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

Без OpenAI и без LiteLLM — модель Whisper крутится прямо на хосте, где запущен Helix:

```bash
uv sync --extra telegram --extra voice
# ffmpeg должен быть в PATH (brew install ffmpeg / apt install ffmpeg)

# .env
HELIX_WHISPER_BACKEND=local
HELIX_WHISPER_LOCAL_MODEL=base     # tiny быстрее, small точнее
HELIX_WHISPER_LOCAL_DEVICE=cpu     # cuda + float16 на GPU
HELIX_TELEGRAM_VOICE_LANGUAGE=ru
```

Или `HELIX_WHISPER_BACKEND=auto` — локально, если `faster-whisper` установлен и нет API-ключей.

| Модель | RAM (≈) | Качество |
|--------|---------|----------|
| `tiny` | ~1 GB | базовое |
| `base` | ~1.5 GB | хорошее для команд |
| `small` | ~2.5 GB | лучше для русского |
| `medium` | ~5 GB | высокое |

**Ollama** не подходит для Whisper-транскрибации (нет OpenAI `/audio/transcriptions`).

#### Вариант 3: OpenAI напрямую

```bash
OPENAI_API_KEY=sk-...
HELIX_WHISPER_MODEL=whisper-1
```

**Важно:** Ollama **не** поддерживает Whisper. LiteLLM — да, но модель `whisper` должна быть в его конфиге (проверка: `curl …/v1/models` — в списке есть `whisper`).

### Использование

Отправьте **голосовое сообщение** или **аудиофайл** (mp3/m4a) в чат с ботом — Helix автоматически:
- 🎙️ Покажет "Распознано: ..."
- 🤖 Обработает текст через агента
- 💬 Ответит на ваш запрос

### Ограничения

- Максимальная длительность: ~25 МБ (лимит Telegram)
- Язык: Whisper автоопределяет язык, но можно задать явно (через код)
- Требуется интернет-соединение для API Whisper

### Безопасность

Аудиофайлы временно сохраняются во временной директории и удаляются сразу после транскрибации. Никакие голосовые данные не хранятся постоянно.

После изменения `.env` или настроек голоса:

```bash
helix gateway reload
```
