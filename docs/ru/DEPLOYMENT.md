# Развёртывание

## Docker

```bash
cp .env.example .env
# Задайте HELIX_API_KEY_PEPPER, TELEGRAM_* при необходимости
docker compose up -d
```

В контейнере: `helix gateway start`.

## systemd

Gateway Helix привязан к **профилю**. У каждого профиля свой `.env`, порт gateway, Telegram-бот и состояние в `~/.helix/profiles/<имя>/`.

Файлы unit:

| Файл | Назначение |
|------|------------|
| [deploy/systemd/helix-gateway.service](../../deploy/systemd/helix-gateway.service) | Профиль `default` |
| [deploy/systemd/helix-gateway@.service](../../deploy/systemd/helix-gateway@.service) | Любой именованный профиль (`%i`) |
| [deploy/systemd/helix.conf.example](../../deploy/systemd/helix.conf.example) | Пути к `python` / CLI `helix` |

### 1. Пользователь сервиса

```bash
sudo useradd --system --create-home --home-dir /home/helix --shell /usr/sbin/nologin helix
sudo -u helix pipx install HelixAgentAi
sudo -u helix pipx inject HelixAgentAi telegram   # опционально, для Telegram
```

### 2. Настройка профиля

Секреты и bind gateway — в **env-файле профиля**, не в `/etc/helix/`:

```bash
sudo -u helix helix profile env --edit
# или для именованного профиля:
sudo -u helix helix -p alice profile env --edit
```

Минимум для production:

```bash
HELIX_ENV=production
HELIX_GATEWAY_HOST=127.0.0.1
HELIX_GATEWAY_PORT=8000
HELIX_REQUIRE_AUTH=true
HELIX_API_KEY_PEPPER=<случайный-секрет>
```

Telegram (опционально): `sudo -u helix helix -p alice telegram setup`

### 3. Установка unit-файлов

```bash
sudo mkdir -p /etc/helix
sudo cp deploy/systemd/helix.conf.example /etc/helix/helix.conf
# Отредактируйте HELIX_PYTHON и HELIX_BIN под пути pipx на вашем хосте

sudo cp deploy/systemd/helix-gateway.service /etc/systemd/system/
sudo cp deploy/systemd/helix-gateway@.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Пути pipx:

```bash
sudo -u helix pipx environment HelixAgentAi
# HELIX_PYTHON → .../venvs/helixagentai/bin/python
# HELIX_BIN     → ~/.local/bin/helix
```

### 4. Запуск и управление

**Профиль default:**

```bash
sudo systemctl enable --now helix-gateway
sudo systemctl status helix-gateway
sudo journalctl -u helix-gateway -f
```

**Именованный профиль** (один instance systemd на профиль):

```bash
sudo systemctl enable --now helix-gateway@alice
sudo systemctl enable --now helix-gateway@bob
sudo systemctl status 'helix-gateway@*'
```

У каждого профиля должен быть **свой порт** в `.env`:

```bash
# ~/.helix/profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# ~/.helix/profiles/bob/.env
HELIX_GATEWAY_PORT=8002
```

Остановка / перезапуск одного профиля без влияния на остальные:

```bash
sudo systemctl restart helix-gateway@alice
sudo systemctl stop helix-gateway@bob
```

Логи на диске: `~/.helix/profiles/<имя>/gateway/gateway.log` — также `helix logs -s gateway -f`.

После изменения `.env` профиля: `sudo systemctl restart helix-gateway@<имя>` или `helix -p <имя> gateway reload` при ручном запуске.

### 5. Виджет чата на сайте документации

Ассистент отвечает **только** на вопросы по документации и сайту — без инструментов, команд и доступа к файлам.

В `.env` профиля, с которым запускается gateway + docs:

```bash
HELIX_GATEWAY_WITH_DOCS=1
HELIX_DOCS_CHAT_ENABLED=1
HELIX_DOCS_CHAT_PROFILE=docs
HELIX_DOCS_CHAT_TOKEN=$(openssl rand -hex 24)
```

Создайте профиль `docs` только с ключами LLM:

```bash
helix -p docs profile env --edit
helix -p docs models setup
```

Запуск:

```bash
helix -p default gateway start --with-docs
```

Поведение виджета:
- при **первом** визите чат открывается автоматически;
- если пользователь закрыл чат — при следующих визитах остаётся свёрнутым (`localStorage`).

Токен `HELIX_DOCS_CHAT_TOKEN` используется прокси на docs-сервере (`/api/docs-chat`) и **не** попадает в браузер.

### 6. Reverse proxy (TLS)

Gateway слушает `127.0.0.1` в `.env` профиля, TLS — на nginx/Caddy/Traefik. Отдельный upstream на каждый профиль/порт.

См. также: [PROFILES.md](PROFILES.md), [GATEWAY.md](GATEWAY.md), [SECURITY.md](SECURITY.md).

## CI

GitHub Actions: `.github/workflows/ci.yml` — ruff, pytest, `helix doctor --no-llm`.

## TLS

Gateway на `127.0.0.1`, TLS на nginx/Caddy/Traefik.