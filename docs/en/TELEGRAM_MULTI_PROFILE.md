# Telegram: multiple isolated profiles

How to run Helix in Telegram when you need several users or projects with isolated data, memory, and settings.

See also: [TELEGRAM.md](TELEGRAM.md), [PROFILES.md](PROFILES.md), [DEPLOYMENT.md](DEPLOYMENT.md).

---

## How Helix is designed

Each **profile** has its own isolated environment:

| Resource | Path |
|----------|------|
| Secrets, LLM, ports | `~/.helix/profiles/<name>/.env` |
| Telegram bot | `~/.helix/profiles/<name>/telegram.env` |
| Gateway | `~/.helix/profiles/<name>/gateway/` |
| Memory, skills, cron | `~/.helix/profiles/<name>/data/` |

**Important:** one Telegram bot token = one polling process = one profile at startup. Helix does **not** run multiple fully isolated profiles in parallel on the **same** bot token.

Documented pattern:

> **Different people → different profiles → different bots**

```bash
helix -p alice telegram setup   # own token from @BotFather
helix -p bob telegram setup     # another token
```

Each gateway starts **its own** bot:

```bash
helix -p alice gateway start   # Alice bot + gateway :8001
helix -p bob gateway start     # Bob bot + gateway :8002
```

Use different ports in each profile `.env`:

```bash
# ~/.helix/profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# ~/.helix/profiles/bob/.env
HELIX_GATEWAY_PORT=8002
```

This is the **recommended** setup for multiple users with full isolation.

---

## Recommended: one bot per profile

### 1. Create profiles

```bash
helix profile create alice
helix profile create bob --protect   # optional: access key hp_…
```

### 2. Configure env and jail (optional)

```bash
helix -p alice profile env --edit
helix -p bob profile env --edit
helix -p bob profile jail enable /home/bob/projects   # own folder only
```

### 3. One bot per profile

Create a **separate bot** in [@BotFather](https://t.me/BotFather) for each profile:

```bash
helix -p alice telegram setup
helix -p bob telegram setup
```

Token and allowlist are stored in `profiles/<name>/telegram.env`.

### 4. Start gateway (and bot) per profile

```bash
helix -p alice gateway start
helix -p bob gateway start
```

Or via systemd — one unit per profile:

```bash
sudo systemctl enable --now helix-gateway@alice
sudo systemctl enable --now helix-gateway@bob
```

See [DEPLOYMENT.md](DEPLOYMENT.md).

### 5. Restrict access in production

For a **personal** bot (one owner), set your user id in `telegram.env` or profile `.env`:

```bash
HELIX_ENV=production
HELIX_TELEGRAM_ALLOWED_USERS=123456789
```

For a **shared** bot with many users, use access requests instead (next section).

---

## One bot — many users (access requests, recommended)

One token, many isolated users — no manual user ids during setup.

```bash
helix -p shared telegram setup
HELIX_ENV=production helix -p shared gateway start -f
```

1. **Bootstrap** (once): designate the Telegram admin from CLI — `helix -p shared telegram requests approve USER_ID --set-admin` (creates profile `admin`, CLI only).
2. Users send `/start` in Telegram (menu hidden until approved); the admin gets a Telegram notification.
3. Admin approves from CLI:

```bash
helix -p shared telegram requests list
helix -p shared telegram requests approve USER_ID -i
helix -p shared telegram requests approve USER_ID --create-profile ivan
```

On approve Helix creates a **protected** profile (with `--create-profile`), enables **workspace jail** at `profiles/ivan/workspace/`, binds the user, **sends the access key in Telegram**, and enables the slash menu for that chat.

- Use a **named bot profile** (`-p shared`), not `default` — `default` is dev-only in production.
- `HELIX_TELEGRAM_ACCESS_REQUESTS=true` is set by `telegram setup` (see [TELEGRAM.md](TELEGRAM.md)).
- No bot restart needed after approve.

---

## Alternative: one bot + manual `/profile` or `map`

For a **trusted team** that manages bindings explicitly (without access requests).

```bash
helix -p shared gateway start
```

Each user switches manually: `/profile alice` or `/profile bob hp_xxxxxxxx` (protected profiles).  
Or bind user ids: `helix telegram map set …` (see below).

### Limits of a single bot

| Limit | Explanation |
|-------|-------------|
| Auto `user_id → profile` | `helix telegram map` or `telegram requests approve` |
| New chat | Starts on the profile active when `gateway start` was run |
| One token | Cannot run two profiles as independent bots on one token |
| Security | Shared bot; isolation relies on per-user profiles, keys, and jail |

### Hardening with one bot

```bash
helix profile create alice --protect
helix profile create bob --protect
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
- **Same `HELIX_GATEWAY_PORT`** across profiles — the second gateway will not start.
- **No access path in production** — with `HELIX_ENV=production`, users need access requests, allowlist, or `map` bindings.

Check:

```bash
helix doctor
helix -p alice gateway status
helix -p bob gateway status
helix logs -s gateway -n 50
```

---

## Summary

- **Full isolation** → separate bot (token) + separate gateway per profile.
- **One bot, many users** → `telegram setup` + `telegram requests approve --create-profile` (recommended).
- **Manual team setup** → `map` bindings or `/profile` with protected profiles and jail.

## User id → profile mapping (single bot, manual)

`helix telegram setup` offers bindings when multiple Helix profiles exist.

```bash
helix -p shared telegram map set 123456789 alice
helix -p shared telegram map bind bob --user-id 987654321
helix -p shared telegram map import "111:alice,222:bob"
helix -p shared telegram map list
helix -p shared telegram map remove 111
```

- File: `~/.helix/profiles/<bot-profile>/telegram-users.json`
- Env: `HELIX_TELEGRAM_USER_PROFILES=123456789:alice` in `telegram.env`

Users are routed to their profile automatically (memory, models, jail).  
Manual `/profile` disables auto-routing for that chat.