# Deployment

## Docker

```bash
cp .env.example .env
# Set HELIX_API_KEY_PEPPER, TELEGRAM_* as needed
docker compose up -d
```

Uses `helix gateway start` inside the container.

## systemd

Helix gateway is **scoped to a profile**. Each profile has its own `.env`, gateway port, Telegram bot, and state under `~/.helix/profiles/<name>/`.

Unit files:

| File | Purpose |
|------|---------|
| [deploy/systemd/helix-gateway.service](../../deploy/systemd/helix-gateway.service) | Profile `default` |
| [deploy/systemd/helix-gateway@.service](../../deploy/systemd/helix-gateway@.service) | Any named profile (`%i`) |
| [deploy/systemd/helix.conf.example](../../deploy/systemd/helix.conf.example) | Paths to `python` / `helix` CLI |

### 1. Prepare the service user

```bash
sudo useradd --system --create-home --home-dir /home/helix --shell /usr/sbin/nologin helix
sudo -u helix pipx install HelixAgentAi
sudo -u helix pipx inject HelixAgentAi telegram   # optional, for Telegram bot
```

### 2. Configure the profile

Secrets and gateway bind go into the **profile** env file, not `/etc/helix/`:

```bash
sudo -u helix helix profile env --edit
# or for a named profile:
sudo -u helix helix -p alice profile env --edit
```

Minimum for production:

```bash
HELIX_ENV=production
HELIX_GATEWAY_HOST=127.0.0.1
HELIX_GATEWAY_PORT=8000
HELIX_REQUIRE_AUTH=true
HELIX_API_KEY_PEPPER=<random-secret>
```

Telegram (optional): `sudo -u helix helix -p alice telegram setup`

### 3. Install unit files

```bash
sudo mkdir -p /etc/helix
sudo cp deploy/systemd/helix.conf.example /etc/helix/helix.conf
# Edit HELIX_PYTHON and HELIX_BIN to match pipx paths on your host

sudo cp deploy/systemd/helix-gateway.service /etc/systemd/system/
sudo cp deploy/systemd/helix-gateway@.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Find pipx paths:

```bash
sudo -u helix pipx environment HelixAgentAi
# HELIX_PYTHON → .../venvs/helixagentai/bin/python
# HELIX_BIN     → ~/.local/bin/helix
```

### 4. Start and manage

**Default profile:**

```bash
sudo systemctl enable --now helix-gateway
sudo systemctl status helix-gateway
sudo journalctl -u helix-gateway -f
```

**Named profile** (one systemd instance per profile):

```bash
sudo systemctl enable --now helix-gateway@alice
sudo systemctl enable --now helix-gateway@bob
sudo systemctl status 'helix-gateway@*'
```

Each profile must use a **different port** in its `.env`:

```bash
# ~/.helix/profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# ~/.helix/profiles/bob/.env
HELIX_GATEWAY_PORT=8002
```

Stop / restart a single profile without affecting others:

```bash
sudo systemctl restart helix-gateway@alice
sudo systemctl stop helix-gateway@bob
```

Logs on disk: `~/.helix/profiles/<name>/gateway/gateway.log` — also `helix logs -s gateway -f`.

After changing profile `.env`: `sudo systemctl restart helix-gateway@<name>` or `helix -p <name> gateway reload` when running manually.

### 5. Documentation-site chat widget

The assistant answers **only** documentation and website questions — no tools, commands, or file access.

In the profile `.env` used when starting gateway + docs:

```bash
HELIX_GATEWAY_WITH_DOCS=1
HELIX_DOCS_CHAT_ENABLED=1
HELIX_DOCS_CHAT_PROFILE=docs
HELIX_DOCS_CHAT_TOKEN=$(openssl rand -hex 24)
```

Create a `docs` profile with LLM credentials only:

```bash
helix -p docs profile env --edit
helix -p docs models setup
```

Start:

```bash
helix -p default gateway start --with-docs
```

Widget behaviour:
- **first visit** — chat opens automatically;
- if the user closed it — stays collapsed on later visits (`localStorage`).

`HELIX_DOCS_CHAT_TOKEN` is used by the docs-server proxy (`/api/docs-chat`) and is **not** exposed to the browser.

### 6. Reverse proxy (TLS)

Bind gateway to `127.0.0.1` in the profile `.env` and terminate TLS at nginx/Caddy/Traefik. One upstream per profile/port.

See also: [PROFILES.md](PROFILES.md), [GATEWAY.md](GATEWAY.md), [SECURITY.md](SECURITY.md).

## CI

GitHub Actions: `.github/workflows/ci.yml` — ruff, pytest, `helix doctor --no-llm`.

## TLS

Bind gateway to `127.0.0.1` and terminate TLS at nginx/Caddy/Traefik.