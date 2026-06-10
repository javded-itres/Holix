# Telegram

**Community channel:** [t.me/helix_agent](https://t.me/helix_agent) — project news and updates (not the bot you configure below).

Each profile can use its **own bot**. Secrets are stored in:

`~/.helix/profiles/<name>/telegram.env`

```bash
uv sync --extra telegram
helix -p shared telegram setup    # wizard: bot token only
helix -p shared gateway start -f  # gateway + Telegram bot
```

## One bot — many users (recommended)

One Telegram token can serve many people. You do **not** enter user ids during setup.

### 1. Admin: connect the bot

```bash
helix -p shared telegram setup
HELIX_ENV=production helix -p shared gateway start -f
```

The wizard saves only the **bot token** and enables **access-request mode** (`HELIX_TELEGRAM_ACCESS_REQUESTS=true` by default).

### 2. Bootstrap: designate the Telegram admin (CLI only)

The **first** approved user can become the single Telegram administrator. This cannot be done from Telegram — only from CLI:

```bash
helix -p shared telegram requests approve USER_ID --set-admin
```

Helix:

- creates the Helix profile **`admin`** (if missing) and binds the user to it
- stores `HELIX_TELEGRAM_ADMIN_USER_ID` in `telegram.env`
- enables the slash-command menu for that user

Check or reset:

```bash
helix -p shared telegram admin show
helix -p shared telegram admin clear   # before assigning another admin
```

### 3. User: request access

1. User opens the bot in Telegram.
2. Sends `/start`.
3. Bot replies that access is pending (no slash menu until approved).
4. The Telegram admin receives a **notification in Telegram** with CLI commands to approve or reject.

### 4. Admin: approve and create an isolated profile

```bash
helix -p shared telegram requests list
helix -p shared telegram requests approve USER_ID -i              # pick existing or create new
helix -p shared telegram requests approve USER_ID --create-profile ivan
```

On approve Helix:

- creates a **protected** profile `ivan` with access key `hp_…`
- enables **workspace jail** at `~/.helix/profiles/ivan/workspace/`
- binds the Telegram user to that profile
- **sends the access key to the user in Telegram** (shown once)

The user can message the bot immediately — no bot restart required.

Other commands:

```bash
helix -p shared telegram requests approve USER_ID --profile existing   # existing open profile
helix -p shared telegram requests reject USER_ID
helix -p shared telegram status
helix -p shared telegram sync-menu   # refresh menu for approved users only
```

### Command menu visibility

The slash-command menu is **hidden by default** for unauthorized users. After approve (or allowlist / `map` binding), Helix enables the menu **per private chat**. Run `helix telegram sync-menu` to push menus for all currently authorized users without restarting the bot.

### Production notes

- Use a **named bot profile** (`-p shared`), not `default` — profile `default` is **dev-only** when `HELIX_ENV=production`.
- Prefer `--create-profile` per user for full isolation (memory, `.env`, workspace).
- Manual allowlist (`HELIX_TELEGRAM_ALLOWED_USERS`) is optional when access requests are enabled.
- Exactly **one** Telegram admin (`HELIX_TELEGRAM_ADMIN_USER_ID`); assign with `requests approve --set-admin` only.

Full guide: [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md).

---

## Multiple bots (full isolation)

Different people → different profiles → different bots:

```bash
helix -p alice telegram setup
helix -p bob telegram setup
helix -p alice gateway start
helix -p bob gateway start
```

## User id → profile mapping (manual)

For teams that manage bindings explicitly:

```bash
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map bind bob --user-id 987654321
helix -p shared telegram map list
```

Files: `profiles/shared/telegram-users.json`, optional `HELIX_TELEGRAM_USER_PROFILES` in `telegram.env`.  
Users are routed automatically; manual `/profile` disables auto-routing for that chat.

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