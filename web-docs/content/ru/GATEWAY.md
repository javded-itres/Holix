# API Gateway

HTTP API (OpenAI-совместимый), Hermes-compatible surface, Holix Management API и companion-сервисы (Telegram + cron при настройке).

**Полный справочник API:** [GATEWAY_API.md](GATEWAY_API.md) — Hermes mapping, `/api/holix/` management, auth, SaaS curl-примеры.

## Команды

Команды gateway относятся к **активному профилю**. Для `default` флаг `-p` не нужен:

```bash
holix gateway start              # фон (host по умолчанию 127.0.0.1)
holix gateway start -f           # передний план
holix gateway start --reload     # dev auto-reload
holix gateway status
holix gateway stop
holix gateway reload
```

Другие профили: `holix -p alice gateway start` и т.д.

У каждого профиля своё состояние и логи:

- Состояние: `~/.holix/profiles/<имя>/gateway/state.json`
- Логи: `~/.holix/profiles/<имя>/gateway/gateway.log` — `holix logs -s gateway -f` ([LOGS.md](LOGS.md))

**Несколько gateway** одновременно (разные профили, разные порты):

```bash
# profiles/alice/.env
HOLIX_GATEWAY_PORT=8001

# profiles/bob/.env
HOLIX_GATEWAY_PORT=8002

holix -p alice gateway start
holix -p bob gateway start
```

Supervisor также запускает **cron** и **Telegram** (если настроены для этого профиля) как companion-процессы.

## Multi-profile gateway (v0.2+)

Один процесс uvicorn обслуживает **несколько профилей Holix**:

- Роутинг: `X-Holix-Profile` → поле `model` → host profile
- Per-profile reload: `POST /api/holix/profiles/{id}/reload` (agent + Telegram + cron)
- Management API: `/api/holix/` — профили, модели, MCP, навыки, Telegram admin

Таблицы эндпоинтов и аутентификация: [GATEWAY_API.md](GATEWAY_API.md).

## Переменные окружения

Задаются в **`.env` профиля** (`holix profile env --edit`):

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HOLIX_GATEWAY_HOST` | `127.0.0.1` | Адрес bind |
| `HOLIX_GATEWAY_PORT` | `8000` | Порт |
| `HOLIX_REQUIRE_AUTH` | `true` | API key обязателен (кроме `/health`, `/v1/health`) |
| `HOLIX_ENV=production` | — | Включает auth и строгие проверки |

Маршруты `/admin/*` **всегда** требуют admin API key.

## Краткая карта эндпоинтов

| Группа | Примеры |
|--------|---------|
| Health | `GET /health`, `GET /v1/health`, `GET /health/detailed` |
| Chat | `POST /v1/chat/completions` |
| Hermes | `GET /v1/models`, `/v1/capabilities`, `/v1/runs`, `/api/sessions`, `/api/jobs` |
| Management | `GET/POST /api/holix/profiles`, `…/models`, `…/telegram`, `…/reload` |
| Admin | `POST /admin/api-keys`, `GET /admin/metrics`, `GET /metrics` (Prometheus) |

## Ключи gateway API

Ключи gateway (`hx_…`) аутентифицируют HTTP-клиентов. **Нет** CLI-команды `holix` для их создания — используйте admin API или Swagger UI.

**Первый admin-ключ** (однократно, когда ключей ещё нет):

```bash
export HOLIX_REQUIRE_AUTH=false
holix gateway start -f
# Создайте admin-ключ (см. ниже), сохраните возвращённый hx_…
# Затем HOLIX_REQUIRE_AUTH=true и перезапуск
```

**Создание ключей** (нужен существующий admin-ключ):

```bash
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys?name=my-app&permissions=read,write&rate_limit=100" \
  -H "Authorization: Bearer hx_admin_…"
```

Или Swagger: `/docs` → **Authorize** → вставьте `hx_…` → `POST /admin/api-keys`.

Ключ показывается **один раз** при создании. Права: `read`, `write`, `execute`, `admin`. См. [GATEWAY_API.md](GATEWAY_API.md) и [SECURITY.md](SECURITY.md).

**Ключи доступа к профилю** (`hp_…`) — отдельный слой для `/api/holix/*`; создаются через `holix profile key init`, не через `/admin/api-keys`.

## Интерактивная документация API

FastAPI отдаёт OpenAPI-документацию на порту gateway (по умолчанию `8000`):

| URL | Формат |
|-----|--------|
| `/docs` | Swagger UI — вызов эндпоинтов в браузере |
| `/redoc` | ReDoc — читаемый справочник |
| `/openapi.json` | Сырая схема OpenAPI 3 |

Пример: `http://127.0.0.1:8000/docs`

### Swagger Authorize

1. Откройте `/docs`
2. Нажмите **Authorize** (иконка замка)
3. В поле **HolixApiKey** вставьте ключ gateway (`hx_…`) — с префиксом `Bearer ` или без
4. **Authorize** → закройте диалог
5. Защищённые эндпоинты отправляют `Authorization: Bearer hx_…` (также принимается `X-API-Key`)

`/health` и `/v1/health` работают без ключа. Остальные маршруты требуют auth при `HOLIX_REQUIRE_AUTH=true`.

## Сайт документации (`--with-docs`)

Запуск сайта документации вместе с gateway:

```bash
holix gateway start --with-docs
# или: HOLIX_GATEWAY_WITH_DOCS=1 holix gateway start
```

SPA документации на companion-порту (по умолчанию `8080`) рядом с API:

| Сайт docs | Содержимое |
|-----------|------------|
| `http://127.0.0.1:8080/docs` | Хаб документации |
| `http://127.0.0.1:8080/docs/gateway-api` | **Полный справочник API** (все эндпоинты, curl) |
| `http://127.0.0.1:8000/docs` | **Swagger UI** на порту gateway — живые запросы |

Сначала соберите контент: `holix docs build`. Виджет docs-chat использует **отдельный** токен (`HOLIX_DOCS_CHAT_TOKEN`) — не ключ gateway `hx_`. См. [DEPLOYMENT.md](DEPLOYMENT.md).

## Метрики

Два эндпоинта метрик — оба требуют **admin** API key:

| Эндпоинт | Формат | Описание |
|----------|--------|----------|
| `GET /metrics` | Prometheus text | Корневой scrape target (типично для Prometheus) |
| `GET /admin/metrics` | JSON | Счётчики и сводка в памяти (поля `metrics`, `summary`) |
| `GET /admin/metrics/prometheus` | Prometheus text | Тот же Prometheus-вывод, что и `/metrics` (скрыт из OpenAPI) |

Отключены при `HOLIX_ENABLE_PROMETHEUS_METRICS=false` — `/metrics` и `/admin/metrics/prometheus` возвращают 404; JSON `/admin/metrics` работает.