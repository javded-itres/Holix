# MAX: Multiple Isolated Profiles

How to run Holix on MAX when you need several users or projects with isolated data, memory, and settings.

See also: [MAX.md](MAX.md), [PROFILES.md](PROFILES.md), [DEPLOYMENT.md](DEPLOYMENT.md).

---

## How Holix organizes profiles

Each **profile** has its own isolated environment:

| Resource | Path |
|----------|------|
| Secrets, LLM, ports | `~/.holix/profiles/<name>/.env` |
| MAX bot | `~/.holix/profiles/<name>/max.env` |
| Gateway | `~/.holix/profiles/<name>/gateway/` |
| Memory, skills, cron | `~/.holix/profiles/<name>/data/` |

**Important:** one MAX bot token = one host profile = one webhook (or one polling process). Holix does **not** run multiple fully isolated host profiles in parallel on the **same** bot token.

Recommended pattern for full isolation:

> **Different people → different profiles → different bots**

```bash
holix -p alice max setup   # own token from business.max.ru
holix -p bob max setup     # another token
```

Each gateway starts **its own** bot and webhook:

```bash
holix -p alice gateway start   # Alice bot + gateway :8001
holix -p bob gateway start       # Bob bot + gateway :8002
```

Ports and webhook URLs must differ per profile:

```bash
# ~/.holix/profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# ~/.holix/profiles/alice/max.env
HOLIX_MAX_WEBHOOK_URL=https://alice.example.com/max/webhook

# ~/.holix/profiles/bob/.env
HOLIX_GATEWAY_PORT=8002

# ~/.holix/profiles/bob/max.env
HOLIX_MAX_WEBHOOK_URL=https://bob.example.com/max/webhook
```

This is the **recommended** setup for multiple users with full isolation.

---

## Recommended: one bot per profile

### 1. Create profiles

```bash
holix profile create alice
holix profile create bob --protect   # optional: hp_… access key
```

### 2. Configure the bot in each profile

```bash
holix -p alice max setup
holix -p bob max setup
```

### 3. Start gateways

```bash
holix -p alice gateway start
holix -p bob gateway start
```

Each user messages **their own** bot in MAX.

---

## Alternative: one bot — many Holix profiles

One MAX token on host profile `shared`; each user gets **their own** Holix profile via access requests or `map`.

```bash
holix -p shared max setup
HOLIX_ENV=production holix -p shared gateway start -f
```

Flow:

1. User sends `/start` in MAX
2. Admin runs `holix -p shared max requests approve USER_ID --create-profile ivan`
3. User `ivan` messages the bot; the agent runs in `~/.holix/profiles/ivan/`

Bindings live in `profiles/shared/max-users.json` and the Management API:

```bash
holix -p shared max map list
curl -H "Authorization: Bearer hx_…" \
  http://127.0.0.1:8000/api/holix/profiles/shared/max/map
```

After changes:

```bash
holix -p shared gateway reload
```

### When to use a shared bot

| Criterion | One bot (`shared`) | Bot per profile |
|-----------|-------------------|-----------------|
| Data isolation | Via `map` / access requests | Full by default |
| Operations | One webhook, one token | N webhook URLs, N tokens |
| Scale | Team / SaaS with admin | Independent clients |

---

## Security

- Do not use `HOLIX_MAX_ALLOW_ALL=true` in production.
- Assign **one** MAX admin: `holix max requests approve … --set-admin`.
- Use `--create-profile` and workspace jail for user data.
- Encrypt `max.env` via [profile encryption](PROFILE_ENCRYPTION.md).
- Set webhook secret (`HOLIX_MAX_WEBHOOK_SECRET`) on public endpoints.

---

## Management API (summary)

| Endpoint | Purpose |
|----------|---------|
| `GET …/max/status` | Token (masked), mode, admin, subscriptions |
| `GET/POST …/max/requests` | Access request queue |
| `GET/PUT …/max/map` | user_id → profile bindings |
| `GET/DELETE …/max/admin` | MAX administrator |

Full reference: [GATEWAY_API.md](GATEWAY_API.md).

---

## See also

- [MAX.md](MAX.md) — quickstart, variables, troubleshooting
- [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md) — same pattern for Telegram
- [GATEWAY.md](GATEWAY.md) — multi-profile gateway and companions