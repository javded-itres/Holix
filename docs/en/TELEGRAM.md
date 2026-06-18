# Telegram

**Community channel:** [t.me/helix_agent](https://t.me/helix_agent) — project news and updates (not the bot you configure below).

Each profile can use its **own bot**. Secrets are stored in:

`~/.holix/profiles/<name>/telegram.env`

```bash
uv sync --extra telegram
holix -p shared telegram setup    # wizard: bot token only
holix -p shared gateway start -f  # gateway + Telegram bot
```

### Token storage and loading

- Store the bot token in `profiles/<bot-host>/telegram.env`. When [profile encryption](CONFIGURATION.md#profile-encryption-optional) is enabled, this file is encrypted at rest.
- Do **not** leave an empty `TELEGRAM_BOT_TOKEN=` in `global/.env` — it prevents loading the real token from `telegram.env`. Omit the key in global entirely; Holix fills it from the profile file (including decrypted values when `HOLIX_UNLOCK_KEY` is set).
- Gateway workers call `load_telegram_env_files()` on startup after profile unlock so encrypted tokens are available before the bot starts.

### Production install (`uv tool install`)

When Holix is installed as a global tool, add aiogram explicitly:

```bash
uv tool install ~/Holix --force --with aiogram --with pypdf
```

Without aiogram the gateway logs `Telegram bot skipped: aiogram is not installed` even when the token is configured.

### Profile deletion notice

When an admin deletes a user profile (`holix profile delete` or `DELETE /api/holix/profiles/{id}`), Holix sends a Telegram message to every user mapped to that profile **before** removing data. Use `--skip-notify` or `?notify=false` to skip. See [PROFILES.md](PROFILES.md#deleting-a-profile).

## One bot — many users (recommended)

One Telegram token can serve many people. You do **not** enter user ids during setup.

### 1. Admin: connect the bot

```bash
holix -p shared telegram setup
HOLIX_ENV=production holix -p shared gateway start -f
```

The wizard saves only the **bot token** and enables **access-request mode** (`HOLIX_TELEGRAM_ACCESS_REQUESTS=true` by default).

### 2. Bootstrap: designate the Telegram admin (CLI only)

The **first** approved user can become the single Telegram administrator. This cannot be done from Telegram — only from CLI:

```bash
holix -p shared telegram requests approve USER_ID --set-admin
```

Holix:

- creates the Holix profile **`admin`** (if missing) and binds the user to it
- stores `HOLIX_TELEGRAM_ADMIN_USER_ID` in `telegram.env`
- enables the slash-command menu for that user

Check or reset:

```bash
holix -p shared telegram admin show
holix -p shared telegram admin clear   # before assigning another admin
```

### 3. User: request access

1. User opens the bot in Telegram.
2. Sends `/start`.
3. Bot replies that access is pending (no slash menu until approved).
4. The Telegram admin receives a **notification in Telegram** with CLI commands to approve or reject.

### 4. Admin: approve and create an isolated profile

```bash
holix -p shared telegram requests list
holix -p shared telegram requests approve USER_ID -i              # pick existing or create new
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

On approve Holix:

- creates a **protected** profile `ivan` with access key `hp_…`
- enables **workspace jail** at `~/.holix/profiles/ivan/workspace/`
- binds the Telegram user to that profile
- **sends the access key to the user in Telegram** (shown once)

The user can message the bot immediately — no bot restart required.

> **Paths in bot replies:** approved users with workspace jail see **relative paths only** (`docs/report.pdf`, not `~/.holix/profiles/ivan/workspace/…`). The **Telegram admin** (`HOLIX_TELEGRAM_ADMIN_USER_ID`) still sees full absolute paths. Details: [Path visibility in responses](PROFILES.md#path-visibility-in-responses).

Other commands:

```bash
holix -p shared telegram requests approve USER_ID --profile existing   # existing open profile
holix -p shared telegram requests reject USER_ID
holix -p shared telegram status
holix -p shared telegram sync-menu   # refresh menu for approved users only
```

### Command menu visibility

The slash-command menu is **hidden by default** for unauthorized users. After approve (or allowlist / `map` binding), Holix enables the menu **per private chat**. Run `holix telegram sync-menu` to push menus for all currently authorized users without restarting the bot.

### Production notes

- Use a **named bot profile** (`-p shared`), not `default` — profile `default` is **dev-only** when `HOLIX_ENV=production`.
- Prefer `--create-profile` per user for full isolation (memory, `.env`, workspace).
- Manual allowlist (`HOLIX_TELEGRAM_ALLOWED_USERS`) is optional when access requests are enabled.
- Exactly **one** Telegram admin (`HOLIX_TELEGRAM_ADMIN_USER_ID`); assign with `requests approve --set-admin` only.

---

## Multi-profile topologies

Each **profile** has isolated `.env`, `telegram.env`, gateway, memory, and cron under `~/.holix/profiles/<name>/`. See [PROFILES.md](PROFILES.md).

**Rule:** one Telegram bot token = one polling process. You cannot run two fully isolated bots on the **same** token.

| Approach | Isolation | Setup |
|----------|-----------|-------|
| **One bot per profile** (full isolation) | Complete | Separate @BotFather token + gateway per profile |
| **One bot + access requests** (recommended shared) | Per-user profile + jail | This guide § One bot — many users |
| **One bot + `map` / `/profile`** | After manual binding | § Manual mapping below |

### One bot per profile (full isolation)

```bash
holix -p alice telegram setup
holix -p bob telegram setup
# different ports in each profile .env:
# HOLIX_GATEWAY_PORT=8001 / 8002
holix -p alice gateway start
holix -p bob gateway start
```

Or systemd: `holix-gateway@alice`, `holix-gateway@bob` — [DEPLOYMENT.md](DEPLOYMENT.md).

### Manual user → profile mapping

For trusted teams without access requests:

```bash
holix -p shared telegram map set 123456789 alice
holix -p shared telegram map bind bob --user-id 987654321
holix -p shared telegram map import "111:alice,222:bob"
holix -p shared telegram map list
```

- File: `profiles/<bot-host>/telegram-users.json`
- Env: `HOLIX_TELEGRAM_USER_PROFILES=123456789:alice` in `telegram.env`

Users are routed automatically; manual `/profile` disables auto-routing for that chat.

### Common mistakes

- **Same token in multiple `telegram.env` files** — only one poller wins.
- **Same `HOLIX_GATEWAY_PORT`** across profiles — second gateway fails to bind.
- **Production without access path** — use access requests, allowlist, or `map`.

```bash
holix doctor
holix -p shared gateway status
holix logs -s gateway -n 50
```

## Voice messages

Holix transcribes Telegram **voice notes** and **audio** attachments via the OpenAI Whisper API, then processes the text like a normal message.

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

Holix `.env`:

```bash
HOLIX_WHISPER_BASE_URL=http://192.168.88.252:4000/v1
HOLIX_WHISPER_API_KEY=sk-...       # LiteLLM virtual key
HOLIX_WHISPER_MODEL=whisper        # LiteLLM model_name (not whisper-1)
```

Or reuse the profile `litellm` provider: `HOLIX_WHISPER_USE_PROFILE_LITELLM=true`.

### Option B: Local on the agent machine (offline)

Run Whisper locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — no cloud API:

```bash
uv sync --extra telegram --extra voice
# ffmpeg required on PATH

HOLIX_WHISPER_BACKEND=local
HOLIX_WHISPER_LOCAL_MODEL=base
HOLIX_WHISPER_LOCAL_DEVICE=cpu
HOLIX_TELEGRAM_VOICE_LANGUAGE=ru
```

`HOLIX_WHISPER_BACKEND=auto` uses local when `faster-whisper` is installed and no API keys are set.

Ollama does **not** expose Whisper transcription; use `faster-whisper` or LiteLLM/OpenAI API.

### Option C: OpenAI direct

```bash
OPENAI_API_KEY=sk-...
HOLIX_WHISPER_MODEL=whisper-1
HOLIX_TELEGRAM_VOICE_LANGUAGE=ru
HOLIX_TELEGRAM_VOICE_ENABLED=true
```

Ollama does not host Whisper; LiteLLM does if `whisper` appears in `GET /v1/models`.

### Usage

Send a voice message to the bot. Holix will:

1. Show **Распознано:** with a text preview
2. Run the agent on the transcribed text
3. Reply as usual

Audio files (mp3/m4a) sent as attachments are supported too.

Temporary audio files are deleted immediately after transcription.

## Scheduled tasks (cron)

Gateway must be running (`holix gateway start`). Manage jobs with `/cron` (inline menu) or CLI `holix cron list`.

**Auto-create (0.1.16+):** write a recurring request in plain language — for example:

- `Присылай новости каждый день в 10 утра`
- `Send me a disk usage summary every Monday at 9`

Holix creates the job and replies with id and next run time. Results can be delivered back to the same Telegram chat. Full guide: [CRON.md](CRON.md).

`/stop` cancels the running agent, sub-agents, and pending confirmations without deleting cron jobs.

After changing `.env` or voice settings, apply them with:

```bash
holix gateway reload
```