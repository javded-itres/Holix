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

In `telegram.env` or profile `.env`:

```bash
HELIX_ENV=production
HELIX_TELEGRAM_ALLOWED_USERS=123456789   # your Telegram user id only
```

Get your id via [@userinfobot](https://t.me/userinfobot).

---

## Alternative: one bot for everyone (with limits)

Suitable for a **trusted team** sharing one bot and switching profiles manually.

```bash
helix -p shared gateway start
```

In Telegram each user:

1. Messages the bot.
2. Switches: `/profile alice` or `/profile bob hp_xxxxxxxx` (if the profile is protected).
3. Works in their profile (memory and sessions: `tg_<profile>_<chat_id>`).

The **Profile** menu button and `/profile` without args also list profiles.

### Limits of a single bot

| Limit | Explanation |
|-------|-------------|
| Auto `user_id → profile` mapping | `helix telegram map` (see below) |
| New chat | Starts on the profile used when `gateway start` was run |
| One token | Cannot run two profiles as independent bots on one token |
| Security | Everyone sees the same bot; isolation relies on `/profile`, keys, and jail |

### Hardening with one bot

```bash
helix profile create alice --protect
helix profile create bob --protect
```

Enter a protected profile:

```text
/profile bob hp_xxxxxxxx
```

Plus **workspace jail** — restrict file and terminal tools to one directory:

```bash
helix -p alice profile jail enable /home/alice/work
helix -p bob profile jail enable /home/bob/work
```

See [PROFILES.md](PROFILES.md) — access keys and workspace jail.

---

## Comparison

| Approach | Isolation | Convenience | Security |
|----------|-----------|-------------|----------|
| **1 bot = 1 profile** (recommended) | Full | Each user has their own bot | High |
| **1 bot + `/profile`** | After manual switch | One bot for all | Medium (keys + jail + allowlist) |

---

## Common mistakes

- **Same token in multiple `telegram.env` files** — only one process can poll; others fail with a conflict.
- **Same `HELIX_GATEWAY_PORT`** across profiles — the second gateway will not start.
- **Empty `HELIX_TELEGRAM_ALLOWED_USERS` in production** — bot rejects messages when `HELIX_ENV=production`.

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
- **One bot for a team** → protected profiles, jail, `HELIX_TELEGRAM_ALLOWED_USERS`, switch via `/profile`.

## User id → profile mapping (single bot)

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