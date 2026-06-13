# Deployment

## Docker

Minimal start (only Telegram bot token required):

```bash
export TELEGRAM_BOT_TOKEN="123456789:AAH..."
docker compose up -d
```

The image includes all optional extras (Telegram, voice, browser). On first run it bootstraps `HOLIX_HOME` and saves the bot token. Users send `/start` in Telegram; you approve them from the container:

```bash
docker compose exec holix holix -p shared telegram requests list
docker compose exec holix holix -p shared telegram requests approve USER_ID --create-profile alice
# or bind to an existing profile:
docker compose exec holix holix -p shared telegram requests approve USER_ID --profile existing
```

Use a **named** bot profile (`-p shared` or your bootstrap profile). Profile `default` is dev-only when `HOLIX_ENV=production`.

Optional: set `HOLIX_API_KEY_PEPPER`, `MODEL`, `BASE_URL` (e.g. cloud LLM instead of bundled Ollama).

Uses `holix gateway start -f` with gateway, Telegram bot, and cron in one process.

## systemd

Holix gateway is **scoped to a profile**. Each profile has its own `.env`, gateway port, Telegram bot, and state under `~/.holix/profiles/<name>/`.

Unit files:

| File | Purpose |
|------|---------|
| [deploy/systemd/holix-gateway.service](../../deploy/systemd/holix-gateway.service) | Profile `default` |
| [deploy/systemd/holix-gateway@.service](../../deploy/systemd/holix-gateway@.service) | Any named profile (`%i`) |
| [deploy/systemd/holix.conf.example](../../deploy/systemd/holix.conf.example) | Paths to `python` / `holix` CLI |

### 1. Prepare the service user

```bash
sudo useradd --system --create-home --home-dir /home/holix --shell /usr/sbin/nologin holix
sudo -u holix pipx install Holix
sudo -u holix pipx inject Holix telegram   # optional, for Telegram bot
```

From a source checkout with **uv** (common on dev servers):

```bash
uv tool install /opt/holix --force --with aiogram --with pypdf
```

`uv tool install` does not include the `telegram` extra by default — without `--with aiogram` the gateway starts but the bot stays disabled.

### 2. Configure the profile

Secrets and gateway bind go into the **profile** env file, not `/etc/holix/`:

```bash
sudo -u holix holix profile env --edit
# or for a named profile:
sudo -u holix holix -p alice profile env --edit
```

Minimum for production:

```bash
HOLIX_ENV=production
HOLIX_GATEWAY_HOST=127.0.0.1
HOLIX_GATEWAY_PORT=8000
HOLIX_REQUIRE_AUTH=true
HOLIX_API_KEY_PEPPER=<random-secret>
```

Telegram (optional): `sudo -u holix holix -p alice telegram setup`

Store the bot token in `profiles/<name>/telegram.env`, not as an empty `TELEGRAM_BOT_TOKEN=` line in `global/.env`.

**Encrypted profiles:** add `HOLIX_UNLOCK_KEY` to `global/.env` or the profile `.env` so gateway can decrypt `telegram.env` and memory on startup. After changing secrets, restart: `systemctl restart holix-gateway@<name>`.

**Legacy encrypted workspace:** one-time migration to plaintext (git-friendly):

```bash
holix profile crypto decrypt-workspace --all --yes
# or: deploy/scripts/holix-decrypt-workspaces.sh
```

### 3. Install unit files

```bash
sudo mkdir -p /etc/holix
sudo cp deploy/systemd/holix.conf.example /etc/holix/holix.conf
# Edit HOLIX_PYTHON and HOLIX_BIN to match pipx paths on your host

sudo cp deploy/systemd/holix-gateway.service /etc/systemd/system/
sudo cp deploy/systemd/holix-gateway@.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Find pipx paths:

```bash
sudo -u holix pipx environment Holix
# HOLIX_PYTHON → .../venvs/holix/bin/python
# HOLIX_BIN     → ~/.local/bin/holix
```

### 4. Start and manage

**Default profile:**

```bash
sudo systemctl enable --now holix-gateway
sudo systemctl status holix-gateway
sudo journalctl -u holix-gateway -f
```

**Named profile** (one systemd instance per profile):

```bash
sudo systemctl enable --now holix-gateway@alice
sudo systemctl enable --now holix-gateway@bob
sudo systemctl status 'holix-gateway@*'
```

Each profile must use a **different port** in its `.env`:

```bash
# ~/.holix/profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# ~/.holix/profiles/bob/.env
HOLIX_GATEWAY_PORT=8002
```

Stop / restart a single profile without affecting others:

```bash
sudo systemctl restart holix-gateway@alice
sudo systemctl stop holix-gateway@bob
```

Logs on disk: `~/.holix/profiles/<name>/gateway/gateway.log` — also `holix logs -s gateway -f`.

After changing profile `.env`: `sudo systemctl restart holix-gateway@<name>` or `holix -p <name> gateway reload` when running manually.

### 5. Documentation-site chat widget

The assistant answers **only** documentation and website questions — no tools, commands, or file access.

In the profile `.env` used when starting gateway + docs:

```bash
HOLIX_GATEWAY_WITH_DOCS=1
HOLIX_DOCS_CHAT_ENABLED=1
HOLIX_DOCS_CHAT_PROFILE=docs
HOLIX_DOCS_CHAT_TOKEN=$(openssl rand -hex 24)
```

Create a `docs` profile with LLM credentials only:

```bash
holix -p docs profile env --edit
holix -p docs models setup
```

Start:

```bash
holix -p default gateway start --with-docs
```

Widget behaviour:
- **first visit** — chat opens automatically;
- if the user closed it — stays collapsed on later visits (`localStorage`);
- shows a thinking indicator until the first streamed token;
- opens the first `/docs/<slug>` link from the assistant reply in the site navigation.

`HOLIX_DOCS_CHAT_TOKEN` is used by the docs-server proxy (`/api/docs-chat`) and is **not** exposed to the browser.

### 6. Documentation site build and SEO

Source markdown lives in `docs/en/` and `docs/ru/`. Rebuild the static site before deploy:

```bash
holix docs build
holix docs              # local preview on :8080
holix gateway start --with-docs
```

`holix docs build` copies content into `web-docs/content/`, rebuilds search index/chunks, `sitemap.xml`, `seo-meta.json`, and crawlable links in `index.html`.

Public URLs (SPA):

| Path | Page |
|------|------|
| `/` | Marketing landing |
| `/docs` | Documentation hub |
| `/docs/<slug>` | Doc page (e.g. `/docs/profiles`) |

Static files at site root: `robots.txt`, `sitemap.xml`, Yandex Webmaster verification (`yandex_*.html`).

After deploy, hard-refresh the browser if assets look stale. Reload gateway after env changes: `holix gateway reload`.

### 7. Reverse proxy (TLS)

Bind gateway to `127.0.0.1` in the profile `.env` and terminate TLS at nginx/Caddy/Traefik. One upstream per profile/port.

See also: [PROFILES.md](PROFILES.md), [GATEWAY.md](GATEWAY.md), [SECURITY.md](SECURITY.md).

## CI

GitHub Actions: `.github/workflows/ci.yml` — ruff, pytest, `holix doctor --no-llm`.

## TLS

Bind gateway to `127.0.0.1` and terminate TLS at nginx/Caddy/Traefik.