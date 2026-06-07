# Развёртывание

## Docker

```bash
cp .env.example .env
# Задайте HELIX_API_KEY_PEPPER, TELEGRAM_* при необходимости
docker compose up -d
```

В контейнере: `helix gateway start`.

## systemd

Пример: [deploy/systemd/helix-gateway.service](../../deploy/systemd/helix-gateway.service)

```bash
sudo cp deploy/systemd/helix-gateway.service /etc/systemd/system/
sudo systemctl enable --now helix-gateway
```

## CI

GitHub Actions: `.github/workflows/ci.yml` — ruff, pytest, `helix doctor --no-llm`.

## TLS

Gateway на `127.0.0.1`, TLS на nginx/Caddy/Traefik.