# Telegram

```bash
uv sync --extra telegram
export TELEGRAM_BOT_TOKEN=...
export HELIX_TELEGRAM_ALLOWED_USERS=123456789
helix telegram
# or with gateway:
helix gateway start
```

Production (`HELIX_ENV=production`) requires `HELIX_TELEGRAM_ALLOWED_USERS`.

One live message per task; slash commands shared with TUI; inline approvals.

## Voice messages

Helix transcribes Telegram **voice notes** and **audio** attachments via the OpenAI Whisper API, then processes the text like a normal message.

### Setup

### Option A: LiteLLM proxy

Add a transcription model to LiteLLM `config.yaml`:

```yaml
model_list:
  - model_name: whisper
    litellm_params:
      model: whisper-1
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      mode: audio_transcription
```

Helix `.env`:

```bash
HELIX_WHISPER_BASE_URL=http://192.168.88.252:4000/v1
HELIX_WHISPER_API_KEY=sk-...       # LiteLLM virtual key
HELIX_WHISPER_MODEL=whisper        # LiteLLM model_name (not whisper-1)
```

Or reuse the profile `litellm` provider: `HELIX_WHISPER_USE_PROFILE_LITELLM=true`.

### Option B: Local on the agent machine (offline)

Run Whisper locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — no cloud API:

```bash
uv sync --extra telegram --extra voice
# ffmpeg required on PATH

HELIX_WHISPER_BACKEND=local
HELIX_WHISPER_LOCAL_MODEL=base
HELIX_WHISPER_LOCAL_DEVICE=cpu
HELIX_TELEGRAM_VOICE_LANGUAGE=ru
```

`HELIX_WHISPER_BACKEND=auto` uses local when `faster-whisper` is installed and no API keys are set.

Ollama does **not** expose Whisper transcription; use `faster-whisper` or LiteLLM/OpenAI API.

### Option C: OpenAI direct

```bash
OPENAI_API_KEY=sk-...
HELIX_WHISPER_MODEL=whisper-1
HELIX_TELEGRAM_VOICE_LANGUAGE=ru
HELIX_TELEGRAM_VOICE_ENABLED=true
```

Ollama does not host Whisper; LiteLLM does if `whisper` appears in `GET /v1/models`.

### Usage

Send a voice message to the bot. Helix will:

1. Show **Распознано:** with a text preview
2. Run the agent on the transcribed text
3. Reply as usual

Audio files (mp3/m4a) sent as attachments are supported too.

Temporary audio files are deleted immediately after transcription.

After changing `.env` or voice settings, apply them with:

```bash
helix gateway reload
```