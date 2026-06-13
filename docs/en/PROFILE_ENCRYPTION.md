# Profile encryption at rest

Holix can encrypt **profile secrets and memory** on disk so backups, stolen disks, and host administrators cannot read API keys, Telegram tokens, agent soul, or conversation history without the user's **unlock key**.

**Workspace files stay plaintext** — project code and documents under `profiles/<name>/workspace/` remain git-friendly and are not encrypted going forward. Legacy encrypted workspace files from older builds are migrated once with `holix profile crypto decrypt-workspace`.

> **Related:** [SECURITY.md](SECURITY.md#encryption-at-rest) · [CONFIGURATION.md](CONFIGURATION.md#profile-encryption-optional) · [CLI.md](CLI.md#holix-profile-crypto) · [DEPLOYMENT.md](DEPLOYMENT.md)

## What is encrypted

| Encrypted at rest | Plaintext (by design) |
|-------------------|------------------------|
| `profiles/<name>/.env` — API keys, ports | `profiles/<name>/config.yaml` — models, MCP (non-secret settings) |
| `profiles/<name>/telegram.env` — bot token, allowlist | `profiles/<name>/workspace/` — agent project files |
| `profiles/<name>/SOUL.md`, `USER.md`, `INIT.md` | `profiles/<name>/gateway/` — PID, logs |
| SQLite memory: `memory.db`, `ltm.db`, `checkpoints.db` | `telegram-users.json` — user id → profile bindings |
| Chroma vector store (sealed as `vector_db.sealed`) | Most files under `data/skills/`, `data/cron/` |

**Format:** files use the `HOLIXENC1` header (AES-256-GCM). Metadata lives in `profiles/<name>/crypto.json` (Argon2id-wrapped DEK).

**Telegram attachments:** when encryption is enabled, files under `workspace/` or `data/files/` are sent to users as **decrypted plaintext** (`materialize_file_for_delivery`) — recipients never receive ciphertext.

## What encryption does *not* protect

While a profile is **unlocked** and the agent is running, a privileged process on the host could read process memory or intercept LLM traffic. Encryption targets **at-rest** data and **offline backups**, not live memory forensics or provider-side prompts.

Losing the unlock key means **data is unrecoverable** — there is no server-side recovery of the DEK without the user key.

## Keys and unlock flow

| Term | Env / file | Role |
|------|------------|------|
| **Unlock key** (UEK) | `HOLIX_UNLOCK_KEY` or prompted | User secret; never stored on disk |
| **DEK** | Wrapped in `crypto.json` | Per-profile data encryption key (random 256-bit) |
| **KEK** | Derived in memory via Argon2id | Unwraps DEK from `crypto.json` when unlock key is supplied |

```mermaid
flowchart LR
  UEK[HOLIX_UNLOCK_KEY] --> KDF[Argon2id + salt]
  KDF --> KEK[KEK in memory]
  KEK --> DEK[DEK unwrap]
  DEK --> SEC[.env telegram.env SOUL memory DBs]
```

**CLI session:** `holix profile crypto unlock` loads the DEK into an in-process session cache.

**Gateway / systemd:** set `HOLIX_UNLOCK_KEY` in `global/.env` or `profiles/<name>/.env` so `gateway_worker` unlocks before reading `telegram.env` and memory.

After gateway stop, `holix-gateway-seal.sh` (systemd `ExecStopPost`) can re-seal memory with the same key.

## Policy by operating system (`HOLIX_ENCRYPTION_MODE`)

Holix applies encryption **only when the global policy allows runtime crypto** *and* the profile has `crypto.json`.

| Mode | Value | Linux server | macOS dev | Windows dev |
|------|-------|--------------|-----------|-------------|
| **Linux production** (default) | `linux-production` | Active when `crypto.json` exists | **Inactive** — files stay readable plaintext unless you enable crypto metadata | **Inactive** |
| **Always on** | `on` | Active | Active | Active |
| **Disabled** | `off` | Inactive | Inactive | Inactive |

```bash
# Default — no variable needed (same as linux-production)
HOLIX_ENCRYPTION_MODE=linux-production

# Force encryption on a Mac or Windows workstation
HOLIX_ENCRYPTION_MODE=on

# Disable entirely (also blocks holix profile crypto enable)
HOLIX_ENCRYPTION_MODE=off
```

### Practical guidance per OS

**Linux (VPS, systemd, Docker production)** — recommended setup:

1. Set `HOLIX_ENV=production` and `HOLIX_ENCRYPTION_MODE=linux-production` (or omit — it is the default).
2. Run `holix profile crypto enable` or `holix profile crypto migrate --all --yes` on the server.
3. Store `HOLIX_UNLOCK_KEY` in `global/.env` (restricted permissions `chmod 600`).
4. Restart gateway after enabling encryption.

**macOS / Windows (local development)** — encryption is **off at runtime** with the default policy, even if `crypto.json` exists. This keeps local debugging simple. To test encrypted profiles locally, set `HOLIX_ENCRYPTION_MODE=on` before `holix profile crypto enable`.

**Enabling crypto on non-Linux with default policy** — `holix profile crypto enable` fails with:

```text
Profile encryption is limited to Linux hosts (HOLIX_ENCRYPTION_MODE=linux-production).
Use HOLIX_ENCRYPTION_MODE=on to force enable on this machine.
```

Check effective policy:

```bash
holix -p alice profile crypto status
```

Example output: `linux-production (active, host=linux)` or `linux-production (inactive, host=other)`.

## Enable encryption (step by step)

### One profile

```bash
holix -p alice profile crypto enable
# prompts twice for unlock key (store it safely — shown only at setup)

holix -p alice profile crypto status
```

Holix creates `crypto.json`, encrypts existing secrets and memory, and decrypts any legacy encrypted workspace files to plaintext.

### All profiles on a server

```bash
holix profile crypto migrate --all --yes
```

Skips profiles that already have `crypto.json`.

### After enable — gateway

Add to `~/.holix/global/.env` or `profiles/<gateway-profile>/.env`:

```bash
HOLIX_UNLOCK_KEY=your-long-random-passphrase
HOLIX_ENCRYPTION_MODE=linux-production
```

```bash
holix -p docs gateway restart
holix -p docs telegram status   # token should show masked, not empty
```

## Daily operations

| Task | Command |
|------|---------|
| Unlock for CLI editing | `holix -p alice profile crypto unlock` |
| Edit encrypted `.env` | `holix -p alice profile env --edit` (temp plaintext file) |
| Check status | `holix -p alice profile crypto status` |
| Re-seal after maintenance | `holix profile crypto seal --all --yes` |
| Lock CLI session | `holix profile crypto lock` |
| Clear stale cache | `holix profile crypto purge-cache` |

## Workspace migration (legacy installs)

Older Holix builds could encrypt files inside `workspace/`. Current policy keeps workspace plaintext.

```bash
# One profile
holix -p alice profile crypto decrypt-workspace --yes

# Entire HOLIX_HOME (servers)
holix profile crypto decrypt-workspace --all --yes
```

Systemd helper: `deploy/scripts/holix-decrypt-workspaces.sh` (reads `HOLIX_UNLOCK_KEY` from `global/.env`).

## Telegram and empty global token

When `telegram.env` is encrypted, gateway must unlock **before** loading the bot token.

Common pitfall: `TELEGRAM_BOT_TOKEN=` (empty) in `global/.env` blocks the real token from `profiles/<name>/telegram.env`. **Remove the empty line** or omit the variable entirely.

Holix now overwrites blank shell/global values when loading `telegram.env`. See [TELEGRAM.md](TELEGRAM.md#token-storage-and-loading) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md#telegram-bot-skipped-at-gateway-start).

## Threat model (summary)

| Threat | Without encryption | With encryption + unlock key only on client |
|--------|-------------------|---------------------------------------------|
| `cat profiles/alice/.env` on server | Plaintext secrets | `HOLIXENC1` ciphertext |
| Stolen disk backup | Full profile data | Ciphertext without unlock key |
| Holix admin / root before unlock | Reads files | Reads ciphertext + metadata only |
| Lost unlock key | — | **Permanent data loss** (by design) |

Profile access keys (`hp_…`) control **who may switch into a profile** — they do not decrypt files. Gateway API keys (`hx_…`) authenticate HTTP — they do not replace `HOLIX_UNLOCK_KEY`.

## CLI reference

```bash
holix profile crypto enable [--unlock-key KEY] [--skip-existing]
holix profile crypto migrate --all [--yes] [--unlock-key KEY]
holix profile crypto status
holix profile crypto unlock [--unlock-key KEY]
holix profile crypto lock
holix profile crypto seal [--all] [--yes]
holix profile crypto decrypt-workspace [--all] [--yes]
holix profile crypto purge-cache
```

Full option list: `holix profile crypto --help`.

## Related

- [PROFILES.md](PROFILES.md) — isolation, delete with Telegram notify
- [DEPLOYMENT.md](DEPLOYMENT.md) — systemd, `HOLIX_UNLOCK_KEY`, `uv tool install --with aiogram`
- [SECURITY.md](SECURITY.md) — production checklist
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Telegram bot skipped, encrypted env