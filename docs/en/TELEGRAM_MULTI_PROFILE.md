# Telegram: multiple isolated profiles

How to run Holix in Telegram when you need several users or projects with isolated data, memory, and settings.

See also: [TELEGRAM.md](TELEGRAM.md), [PROFILES.md](PROFILES.md), [DEPLOYMENT.md](DEPLOYMENT.md).

---

## How Holix is designed

Each **profile** has its own isolated environment:

| Resource | Path |
|----------|------|
| Secrets, LLM, ports | `~/.holix/profiles/<name>/.env` |
| Telegram bot | `~/.holix/profiles/<name>/telegram.env` |
| Gateway | `~/.holix/profiles/<name>/gateway/` |
| Memory, skills, cron | `~/.holix/profiles/<name>/data/` |

**Important:** one Telegram bot token = one polling process = one profile at startup. Holix does **not** run multiple fully isolated profiles in parallel on the **same** bot token.

Documented pattern:

> **Different people → different profiles → different bots**

```bash
holix -p alice telegram setup   # own token from @BotFather
holix -p bob telegram setup     # another token
```

Each gateway starts **its own** bot:

```bash
holix -p alice gateway start   # Alice bot + gateway :8001
holix -p bob gateway start     # Bob bot + gateway :8002
```

Use different ports in each profile `.env`:

```bash
# ~/.holix/profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# ~/.holix/profiles/bob/.env
HOLIX_GATEWAY_PORT=8002
```

This is the **recommended** setup for multiple users with full isolation.

---

## Recommended: one bot per profile

### 1. Create profiles

```bash
holix profile create alice
holix profile create bob --protect   # optional: access key hp_…
```

### 2. Configure env and jail (optional)

```bash
holix -p alice profile env --edit
holix -p bob profile env --edit
holix -p bob profile jail enable /home/bob/projects   # own folder only
```

### 3. One bot per profile

Create a **separate bot** in [@BotFather](https://t.me/BotFather) for each profile:

```bash
holix -p alice telegram setup
holix -p bob telegram setup
```

Token and allowlist are stored in `profiles/<name>/telegram.env`.

### 4. Start gateway (and bot) per profile

```bash
holix -p alice gateway start
holix -p bob gateway start
```

Or via systemd — one unit per profile:

```bash
sudo systemctl enable --now holix-gateway@alice
sudo systemctl enable --now holix-gateway@bob
```

See [DEPLOYMENT.md](DEPLOYMENT.md).

### 5. Restrict access in production

For a **personal** bot (one owner), set your user id in `telegram.env` or profile `.env`:

```bash
HOLIX_ENV=production
HOLIX_TELEGRAM_ALLOWED_USERS=123456789
```

For a **shared** bot with many users, use access requests instead (next section).

---

## One bot — many users (access requests, recommended)

One token, many isolated users — no manual user ids during setup.

```bash
holix -p shared telegram setup
HOLIX_ENV=production holix -p shared gateway start -f
```

1. **Bootstrap** (once): designate the Telegram admin from CLI — `holix -p shared telegram requests approve USER_ID --set-admin` (creates profile `admin`, CLI only).
2. Users send `/start` in Telegram (menu hidden until approved); the admin gets a Telegram notification.
3. Admin approves from CLI:

```bash
holix -p shared telegram requests list
holix -p shared telegram requests approve USER_ID -i
holix -p shared telegram requests approve USER_ID --create-profile ivan
```

On approve Holix creates a **protected** profile (with `--create-profile`), enables **workspace jail** at `profiles/ivan/workspace/`, binds the user, **sends the access key in Telegram**, and enables the slash menu for that chat.

- Use a **named bot profile** (`-p shared`), not `default` — `default` is dev-only in production.
- `HOLIX_TELEGRAM_ACCESS_REQUESTS=true` is set by `telegram setup` (see [TELEGRAM.md](TELEGRAM.md)).
- No bot restart needed after approve.

---

## Alternative: one bot + manual `/profile` or `map`

For a **trusted team** that manages bindings explicitly (without access requests).

```bash
holix -p shared gateway start
```

Each user switches manually: `/profile alice` or `/profile bob hp_xxxxxxxx` (protected profiles).  
Or bind user ids: `holix telegram map set …` (see below).

### Limits of a single bot

| Limit | Explanation |
|-------|-------------|
| Auto `user_id → profile` | `holix telegram map` or `telegram requests approve` |
| New chat | Starts on the profile active when `gateway start` was run |
| One token | Cannot run two profiles as independent bots on one token |
| Security | Shared bot; isolation relies on per-user profiles, keys, and jail |

### Hardening with one bot

```bash
holix profile create alice --protect
holix profile create bob --protect
```

Protected profiles get workspace jail automatically. See [PROFILES.md](PROFILES.md).

---

## Comparison

| Approach | Isolation | Convenience | Security |
|----------|-----------|-------------|----------|
| **1 bot = 1 profile** (full isolation) | Full | Each user has their own bot | High |
| **1 bot + access requests** (recommended shared) | Per-user profile | `/start` → admin approve | High (key + jail) |
| **1 bot + `/profile` / `map`** | After manual setup | One bot for all | Medium |

---

## Common mistakes

- **Same token in multiple `telegram.env` files** — only one process can poll; others fail with a conflict.
- **Same `HOLIX_GATEWAY_PORT`** across profiles — the second gateway will not start.
- **No access path in production** — with `HOLIX_ENV=production`, users need access requests, allowlist, or `map` bindings.

Check:

```bash
holix doctor
holix -p alice gateway status
holix -p bob gateway status
holix logs -s gateway -n 50
```

---

## Summary

- **Full isolation** → separate bot (token) + separate gateway per profile.
- **One bot, many users** → `telegram setup` + `telegram requests approve --create-profile` (recommended).
- **Manual team setup** → `map` bindings or `/profile` with protected profiles and jail.

## User id → profile mapping (single bot, manual)

`holix telegram setup` offers bindings when multiple Holix profiles exist.

```bash
holix -p shared telegram map set 123456789 alice
holix -p shared telegram map bind bob --user-id 987654321
holix -p shared telegram map import "111:alice,222:bob"
holix -p shared telegram map list
holix -p shared telegram map remove 111
```

- File: `~/.holix/profiles/<bot-profile>/telegram-users.json`
- Env: `HOLIX_TELEGRAM_USER_PROFILES=123456789:alice` in `telegram.env`

Users are routed to their profile automatically (memory, models, jail).  
Manual `/profile` disables auto-routing for that chat.