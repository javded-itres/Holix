# API Gateway

HTTP API (совместим с OpenAI) и companion-сервисы (Telegram при настройке).

## Команды

Команды gateway относятся к **активному профилю**. Для `default` флаг `-p` не нужен:

```bash
helix gateway start              # фон (host по умолчанию 127.0.0.1)
helix gateway start -f           # передний план
helix gateway start --reload     # dev auto-reload
helix gateway status
helix gateway stop
helix gateway reload
```

Другие профили: `helix -p alice gateway start` и т.д.

У каждого профиля своё состояние и логи:

- Состояние: `~/.helix/profiles/<имя>/gateway/state.json`
- Логи: `~/.helix/profiles/<имя>/gateway/gateway.log` — `helix logs -s gateway -f` ([LOGS.md](LOGS.md))

**Несколько gateway** одновременно (разные профили, разные порты):

```bash
# profiles/alice/.env
HELIX_GATEWAY_PORT=8001

# profiles/bob/.env
HELIX_GATEWAY_PORT=8002

helix -p alice gateway start
helix -p bob gateway start
```

Supervisor также запускает **cron** и **Telegram** (если настроены для этого профиля) как companion-процессы.

## Переменные окружения

Задаются в **`.env` профиля** (`helix profile env --edit`):

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