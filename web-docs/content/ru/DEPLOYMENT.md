# Развёртывание

## Docker

Минимальный запуск (достаточно токена Telegram-бота):

```bash
export TELEGRAM_BOT_TOKEN="123456789:AAH..."
docker compose up -d
```

Образ включает все опциональные extras (Telegram, voice, browser). При первом запуске создаётся `HOLIX_HOME` и сохраняется токен бота. Пользователи отправляют `/start` в Telegram; вы одобряете из контейнера:

```bash
docker compose exec holix holix -p shared telegram requests list
docker compose exec holix holix -p shared telegram requests approve USER_ID --create-profile alice
# или привязка к существующему профилю:
docker compose exec holix holix -p shared telegram requests approve USER_ID --profile existing
```

Используйте **именованный** профиль бота (`-p shared` или профиль из bootstrap). Профиль `default` в production (`HOLIX_ENV=production`) недоступен.

Опционально: `HOLIX_API_KEY_PEPPER`, `MODEL`, `BASE_URL` (облачная LLM вместо встроенного Ollama).

В контейнере: `holix gateway start -f` — gateway, Telegram-бот и cron в одном процессе.

## systemd

Gateway Holix привязан к **профилю**. У каждого профиля свой `.env`, порт gateway, Telegram-бот и состояние в `~/.holix/profiles/<имя>/`.

Файлы unit:

| Файл | Назначение |
|------|------------|
| [deploy/systemd/holix-gateway.service](../../deploy/systemd/holix-gateway.service) | Профиль `default` |
| [deploy/systemd/holix-gateway@.service](../../deploy/systemd/holix-gateway@.service) | Любой именованный профиль (`%i`) |
| [deploy/systemd/holix.conf.example](../../deploy/systemd/holix.conf.example) | Пути к `python` / CLI `holix` |

### 1. Пользователь сервиса

```bash
sudo useradd --system --create-home --home-dir /home/holix --shell /usr/sbin/nologin holix
sudo -u holix pipx install HelixAgentAi
sudo -u holix pipx inject HolixAgentAi telegram   # опционально, для Telegram
```

### 2. Настройка профиля

Секреты и bind gateway — в **env-файле профиля**, не в `/etc/holix/`:

```bash
sudo -u holix holix profile env --edit
# или для именованного профиля:
sudo -u holix holix -p alice profile env --edit
```

Минимум для production:

```bash
HOLIX_ENV=production
HOLIX_GATEWAY_HOST=127.0.0.1
HOLIX_GATEWAY_PORT=8000
HOLIX_REQUIRE_AUTH=true
HOLIX_API_KEY_PEPPER=<случайный-секрет>
```

Telegram (опционально): `sudo -u holix holix -p alice telegram setup`

### 3. Установка unit-файлов

```bash
sudo mkdir -p /etc/holix
sudo cp deploy/systemd/holix.conf.example /etc/holix/holix.conf
# Отредактируйте HOLIX_PYTHON и HOLIX_BIN под пути pipx на вашем хосте

sudo cp deploy/systemd/holix-gateway.service /etc/systemd/system/
sudo cp deploy/systemd/holix-gateway@.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Пути pipx:

```bash
sudo -u holix pipx environment HolixAgentAi
# HOLIX_PYTHON → .../venvs/holixagentai/bin/python
# HOLIX_BIN     → ~/.local/bin/holix
```

### 4. Запуск и управление

**Профиль default:**

```bash
sudo systemctl enable --now holix-gateway
sudo systemctl status holix-gateway
sudo journalctl -u holix-gateway -f
```

**Именованный профиль** (один instance systemd на профиль):

```bash
sudo systemctl enable --now holix-gateway@alice
sudo systemctl enable --now holix-gateway@bob
sudo systemctl status 'holix-gateway@*'
```

У каждого профиля должен быть **свой порт** в `.env`:

```bash
# ~/.holix/profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# ~/.holix/profiles/bob/.env
HOLIX_GATEWAY_PORT=8002
```

Остановка / перезапуск одного профиля без влияния на остальные:

```bash
sudo systemctl restart holix-gateway@alice
sudo systemctl stop holix-gateway@bob
```

Логи на диске: `~/.holix/profiles/<имя>/gateway/gateway.log` — также `holix logs -s gateway -f`.

После изменения `.env` профиля: `sudo systemctl restart holix-gateway@<имя>` или `holix -p <имя> gateway reload` при ручном запуске.

### 5. Виджет чата на сайте документации

Ассистент отвечает **только** на вопросы по документации и сайту — без инструментов, команд и доступа к файлам.

В `.env` профиля, с которым запускается gateway + docs:

```bash
HOLIX_GATEWAY_WITH_DOCS=1
HOLIX_DOCS_CHAT_ENABLED=1
HOLIX_DOCS_CHAT_PROFILE=docs
HOLIX_DOCS_CHAT_TOKEN=$(openssl rand -hex 24)
```

Создайте профиль `docs` только с ключами LLM:

```bash
holix -p docs profile env --edit
holix -p docs models setup
```

Запуск:

```bash
holix -p default gateway start --with-docs
```

Поведение виджета:
- при **первом** визите чат открывается автоматически;
- если пользователь закрыл чат — при следующих визитах остаётся свёрнутым (`localStorage`);
- показывает индикатор «Думаю…» до первого токена ответа;
- открывает первую ссылку `/docs/<slug>` из ответа ассистента в навигации сайта.

Токен `HOLIX_DOCS_CHAT_TOKEN` используется прокси на docs-сервере (`/api/docs-chat`) и **не** попадает в браузер.

### 6. Сборка сайта документации и SEO

Исходники markdown: `docs/en/` и `docs/ru/`. Перед деплоем пересоберите сайт:

```bash
holix docs build
holix docs              # локальный предпросмотр на :8080
holix gateway start --with-docs
```

`holix docs build` копирует контент в `web-docs/content/`, пересобирает поиск, `sitemap.xml`, `seo-meta.json` и crawlable-ссылки в `index.html`.

Публичные URL (SPA):

| Путь | Страница |
|------|----------|
| `/` | Маркетинговый лендинг |
| `/docs` | Хаб документации |
| `/docs/<slug>` | Раздел (например `/docs/profiles`) |

Статические файлы в корне сайта: `robots.txt`, `sitemap.xml`, файл верификации Яндекс.Вебмастера (`yandex_*.html`).

После деплоя сделайте жёсткое обновление страницы, если ассеты закэшировались. После смены `.env`: `holix gateway reload`.

### 7. Reverse proxy (TLS)

Gateway слушает `127.0.0.1` в `.env` профиля, TLS — на nginx/Caddy/Traefik. Отдельный upstream на каждый профиль/порт.

См. также: [PROFILES.md](PROFILES.md), [GATEWAY.md](GATEWAY.md), [SECURITY.md](SECURITY.md).

## CI

GitHub Actions: `.github/workflows/ci.yml` — ruff, pytest, `holix doctor --no-llm`.

## TLS

Gateway на `127.0.0.1`, TLS на nginx/Caddy/Traefik.