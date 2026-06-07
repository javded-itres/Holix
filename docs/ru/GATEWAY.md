# API Gateway

HTTP API (совместим с OpenAI) и companion-сервисы (Telegram при настройке).

## Команды

```bash
helix gateway start              # фон (host по умолчанию 127.0.0.1)
helix gateway start -f           # передний план
helix gateway start --reload     # dev auto-reload
helix gateway status
helix gateway stop
helix gateway reload
```

Состояние: `{HELIX_HOME}/gateway/state.json` (по умолчанию `~/.helix/gateway/`)  
Логи: `gateway/gateway.log` — просмотр: `helix logs -s gateway -f` ([LOGS.md](LOGS.md))

Supervisor также запускает **cron** и **Telegram** (при настройке) как companion-процессы.

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HELIX_GATEWAY_HOST` | `127.0.0.1` | Адрес bind |
| `HELIX_GATEWAY_PORT` | `8000` | Порт |
| `HELIX_REQUIRE_AUTH` | `false` | API key для `/v1/*` |
| `HELIX_ENV=production` | — | Включает auth и строгие проверки |

Маршруты `/admin/*` **всегда** требуют admin API key.

## Эндпоинты

- `GET /health` — проверка здоровья
- `GET /metrics` — метрики Prometheus
- `POST /v1/chat/completions` — чат OpenAI-формата
- `POST /admin/api-keys` — создать ключ (admin)