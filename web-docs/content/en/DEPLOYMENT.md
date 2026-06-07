# Deployment

## Docker

```bash
cp .env.example .env
# Set HELIX_API_KEY_PEPPER, TELEGRAM_* as needed
docker compose up -d
```

Uses `helix gateway start` inside the container.

## systemd

Example unit: [deploy/systemd/helix-gateway.service](../../deploy/systemd/helix-gateway.service)

```bash
sudo cp deploy/systemd/helix-gateway.service /etc/systemd/system/
sudo systemctl enable --now helix-gateway
```

## CI

GitHub Actions: `.github/workflows/ci.yml` — ruff, pytest, `helix doctor --no-llm`.

## TLS

Bind gateway to `127.0.0.1` and terminate TLS at nginx/Caddy/Traefik.