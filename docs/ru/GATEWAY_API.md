# Helix Gateway API — полный справочник

> **На сайте документации:** `/docs/gateway-api` (тот же текст, что и эта страница).  
> **Живой OpenAPI (вызов запросов):** `http://127.0.0.1:8000/docs` на порту gateway — не на порту сайта docs.

Helix запускает **единый multi-profile HTTP gateway** с тремя публичными поверхностями:

| Поверхность | Префикс | Назначение |
|-------------|---------|------------|
| **Hermes-compatible API** | `/v1`, `/api/sessions`, `/api/jobs` | Drop-in для Open WebUI, LobeChat, Hermes-клиентов |
| **Расширения агента Helix** | `/v1/chat/completions`, permissions, plans | OpenAI chat + разрешения на инструменты + ревью планов |
| **Helix Management API** | `/api/helix/` | SaaS control plane: профили, модели, MCP, навыки, Telegram |

Эксплуатационное руководство (start/stop, порты, логи): [GATEWAY.md](GATEWAY.md).

### Матрица совместимости с Hermes

| Область | Статус | Примечания |
|---------|--------|------------|
| `/v1/chat/completions`, `/v1/responses`, `/v1/runs` | Полная | Bearer + алиасы заголовков `X-Hermes-*` |
| `/v1/models`, `/v1/capabilities`, `/v1/skills`, `/v1/toolsets` | Полная | Capabilities объявляет флаги Hermes |
| `/api/sessions` CRUD + chat/stream | Полная | `source`, `include_children`; персистентность в `~/.helix/data/gateway/sessions.json` |
| `/api/jobs` CRUD + pause/resume/run | Полная | Алиасы тела: `prompt`, `schedule`, `delivery_target`, `skills`, `provider_override` |
| Multimodal (inline images) | Полная | `image_url` / `input_image`; загрузка файлов → `400 unsupported_content_type` |
| SSE tool progress | Полная | `hermes.tool.progress`, `assistant.delta`, `tool.started`, `tool.completed`, `run.completed` |
| DELETE job отменяет in-flight run | Полная | Общий реестр активных cron-запусков |
| Только Helix | Дополнительно | `/api/helix/*`, permissions, plans — нет в Hermes |

---

## Содержание

1. [Базовый URL и интерактивная документация](#базовый-url-и-интерактивная-документация)
2. [Аутентификация](#аутентификация)
3. [Общие понятия](#общие-понятия)
4. [Примеры SaaS-воркфлоу](#примеры-saas-воркфлоу)
5. [Health и информация о gateway](#health-и-информация-о-gateway)
6. [Admin API](#admin-api)
7. [Hermes API (`/v1`)](#hermes-api-v1)
8. [Расширения агента (`/v1`)](#расширения-агента-v1)
9. [Сессии (`/api/sessions`)](#сессии-apisessions)
10. [Cron-задачи (`/api/jobs`)](#cron-задачи-apijobs)
11. [Управление: профили](#управление-профили)
12. [Управление: модели](#управление-модели)
13. [Управление: навыки](#управление-навыки)
14. [Управление: MCP](#управление-mcp)
15. [Управление: config и env](#управление-config-и-env)
16. [Управление: глобальные настройки](#управление-глобальные-настройки)
17. [Управление: Telegram](#управление-telegram)
18. [API чата сайта документации](#api-чата-сайта-документации)
19. [Архитектура multi-profile](#архитектура-multi-profile)
20. [Замечания по безопасности](#замечания-по-безопасности)

---

## Базовый URL и интерактивная документация

Базовый URL по умолчанию (из `.env` профиля):

```text
http://127.0.0.1:8000
```

| Ресурс | URL | Аутентификация |
|--------|-----|----------------|
| Swagger UI | `http://HOST:PORT/docs` | — |
| ReDoc | `http://HOST:PORT/redoc` | — |
| OpenAPI JSON | `http://HOST:PORT/openapi.json` | — |

### Swagger Authorize (один токен для всех запросов)

1. Откройте `/docs`
2. Нажмите **Authorize** (иконка замка)
3. В поле **HelixApiKey** вставьте ключ gateway (`hx_…`) **без** префикса `Bearer` — Swagger добавит его автоматически
4. Попробуйте любой защищённый эндпоинт через **Try it out**

`X-API-Key: hx_…` также работает в curl и коде, но не настраивается через диалог Authorize.

Метаданные gateway (требуется API key):

```bash
curl -sS -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8000/
```

```json
{
  "name": "Helix API",
  "version": "0.2.0",
  "status": "running",
  "host_profile": "default",
  "loaded_profiles": ["default"],
  "require_auth": true
}
```

---

## Аутентификация

В зависимости от маршрута Helix использует до **трёх независимых механизмов аутентификации**.

### Уровень 1 — API key gateway (`hx_…`)

Требуется почти на всех маршрутах при `HELIX_REQUIRE_AUTH=true` (по умолчанию).

| Заголовок | Пример |
|-----------|--------|
| `Authorization` | `Bearer hx_…` |
| `X-API-Key` | `hx_…` |

**Права** (через запятую при создании): `read`, `write`, `execute`, `admin`. См. [SECURITY.md](SECURITY.md).

**Создание ключа** — отдельной CLI-команды пока нет; используйте HTTP или Swagger:

```bash
# Нужен существующий admin key ИЛИ bootstrap с HELIX_REQUIRE_AUTH=false один раз
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -d "name=my-app&permissions=read,write,execute&rate_limit=100"
```

Ответ содержит `api_key` — **показывается один раз**. Храните его в безопасном месте.

**Bootstrap первого admin key:**

```bash
helix profile env --edit   # HELIX_REQUIRE_AUTH=false
helix gateway reload
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys" \
  -d "name=admin&permissions=read,write,execute,admin&rate_limit=1000"
# Сохраните hx_…, установите HELIX_REQUIRE_AUTH=true, helix gateway reload
```

### Уровень 2 — Ключ доступа к профилю (`hp_…`)

Требуется для маршрутов `/api/helix/*` (дополнительно к API key gateway):

```http
X-Helix-Profile-Key: hp_…
```

| Вызывающая сторона | Заголовки | Область |
|--------------------|-----------|---------|
| Владелец профиля | Gateway key + `X-Helix-Profile-Key` для своего профиля | Один профиль |
| Админ платформы | Gateway key с правом `admin` **или** master key admin-профиля | Все профили |

Имя admin-профиля по умолчанию: `admin` (`HELIX_TELEGRAM_ADMIN_PROFILE`).

Ключи профиля создаются через CLI (`helix profile key init`) или Management API (`POST …/key/init`). Это **не** то же самое, что gateway keys `hx_…`.

### Уровень 3 — Токен docs-chat (только для виджета сайта)

Маршруты под `/v1/docs/chat/*` (кроме `/config`) используют `HELIX_DOCS_CHAT_TOKEN`:

| Заголовок | Пример |
|-----------|--------|
| `Authorization` | `Bearer <docs-chat-token>` |
| `X-Docs-Chat-Token` | `<docs-chat-token>` |

Отдельно от API keys gateway. См. [API чата сайта документации](#api-чата-сайта-документации).

### Публичные эндпоинты (без API key gateway)

| Метод | Путь |
|-------|------|
| GET | `/health` |
| GET | `/v1/health` |
| GET | `/health/detailed` |
| GET | `/v1/docs/chat/config` |

---

## Общие понятия

### Маршрутизация профиля

Для chat, Hermes, sessions и jobs профиль определяется в следующем порядке:

1. Заголовок `X-Helix-Profile` или `X-Hermes-Profile`
2. Поле `model` в теле запроса (имя профиля; не `helix`, `helix-agent`, `hermes-agent`)
3. **Host profile** gateway (`HELIX_PROFILE` при старте процесса)

### Заголовки сессии (алиасы)

| Назначение | Helix | Алиас Hermes |
|------------|-------|--------------|
| Id разговора / транскрипта | `X-Helix-Session-Id` | `X-Hermes-Session-Id` |
| Стабильная область памяти | `X-Helix-Session-Key` | `X-Hermes-Session-Key` |

Ключ сессии: максимум 256 символов; управляющие символы отклоняются → `400`.

### `reload_required`

Мутации в management, меняющие конфигурацию работающего агента, возвращают `"reload_required": true`. Применить без перезапуска uvicorn:

```bash
curl -sS -X POST "$HELIX_URL/api/helix/profiles/$PROFILE/reload" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Helix-Profile-Key: $PROFILE_KEY"
```

### Маскирование секретов

Ответы `GET` в management маскируют API keys, токены и чувствительные env-переменные. Открытый текст возвращается **один раз** при create/init/rotate.

### Ошибки

| Код | Значение |
|-----|----------|
| 400 | Невалидное тело, заголовки или бизнес-правило |
| 401 | Отсутствует или невалидный API key / ключ профиля / docs-chat token |
| 403 | Валидный ключ, но недостаточно прав |
| 404 | Ресурс не найден или функция отключена |
| 409 | Конфликт (например, профиль уже существует, admin уже назначен) |
| 429 | Превышен rate limit для ключа |
| 503 | Gateway не инициализирован (registry, key manager, agent) |

### Rate limiting

У каждого API key есть `rate_limit` (запросов в минуту). Docs-chat имеет отдельный `HELIX_DOCS_CHAT_RATE_LIMIT_RPM` на `client_id`.

### Server-Sent Events (SSE)

Потоковые эндпоинты возвращают `text/event-stream`:

- `POST /v1/chat/completions` с `"stream": true`
- `GET /v1/runs/{id}/events`
- `POST /api/sessions/{id}/chat/stream`
- `POST /v1/docs/chat` с `"stream": true`

---

## Примеры SaaS-воркфлоу

```bash
export HELIX_URL=http://127.0.0.1:8000
export ADMIN_KEY=hx_…
export ADMIN_PROFILE_KEY=hp_…

# 1. Создать профиль арендатора (admin)
curl -sS -X POST "$HELIX_URL/api/helix/profiles" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"tenant-42","with_access_key":true}'

# 2. Добавить LLM-провайдера
curl -sS -X POST "$HELIX_URL/api/helix/profiles/tenant-42/models/providers" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "X-Helix-Profile-Key: $ADMIN_PROFILE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"preset_id":"openrouter","skip_test":true}'

# 3. Перезагрузить агента арендатора + companions
curl -sS -X POST "$HELIX_URL/api/helix/profiles/tenant-42/reload" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "X-Helix-Profile-Key: $ADMIN_PROFILE_KEY"

# 4. Чат от имени арендатора (OpenAI client: model = имя профиля)
curl -sS "$HELIX_URL/v1/chat/completions" \
  -H "Authorization: Bearer $TENANT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"tenant-42","messages":[{"role":"user","content":"hi"}]}'
```

Дополнительные примеры — в соответствующих разделах эндпоинтов ниже.

---

## Health и информация о gateway

### `GET /health`

**Аутентификация:** публичный

Базовая проверка живости: `status`, `timestamp`, `agent_ready`, `require_auth`.

```bash
curl -sS http://127.0.0.1:8000/health
```

### `GET /v1/health`

**Аутентификация:** публичный

Минимальный Hermes health: `{"status":"ok"}`.

### `GET /health/detailed`

**Аутентификация:** публичный (без API key)

Расширенная диагностика: `host_profile`, `loaded_profiles`, `active_runs`, `companions` по профилям, bind host/port.

```bash
curl -sS http://127.0.0.1:8000/health/detailed
```

### `GET /`

**Аутентификация:** API key

Версия gateway, host profile, загруженные профили. См. [Базовый URL](#базовый-url-и-интерактивная-документация).

### `GET /metrics`

**Аутентификация:** Admin API key

Prometheus text exposition (при `enable_prometheus_metrics=true`). Тот же формат, что у admin prometheus endpoint.

```bash
curl -sS -H "Authorization: Bearer $ADMIN_KEY" http://127.0.0.1:8000/metrics
```

---

## Admin API

Префикс `/admin`. **Всегда** требуется API key с правом `admin`.

### `POST /admin/api-keys`

Создать новый API key gateway.

**Query-параметры:**

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `name` | обязательный | Человекочитаемая метка |
| `permissions` | `read,write` | Права через запятую |
| `rate_limit` | `100` | Запросов в минуту |

```bash
curl -sS -X POST "http://127.0.0.1:8000/admin/api-keys?name=ci&permissions=read,execute&rate_limit=200" \
  -H "Authorization: Bearer $ADMIN_KEY"
```

**Ответ:** `api_key` (один раз), `name`, `permissions`, `rate_limit`, `warning`.

### `GET /admin/api-keys`

Список активных ключей (только метаданные — без секретных значений).

### `DELETE /admin/api-keys/{key_id}`

Отозвать ключ по числовому `id` из ответа списка (имя path-параметра в OpenAPI: `key_id`; передавайте **id** ключа, а не секрет).

### `GET /admin/metrics`

JSON-метрики приложения + сводка.

### `GET /admin/metrics/prometheus`

Prometheus text (скрыт из схемы OpenAPI; та же семья, что `GET /metrics`).

---

## Hermes API (`/v1`)

Hermes-compatible поверхность. Все маршруты требуют API key gateway, если не указано иное.

Заголовки профиля применяются там, где указано. См. [документацию Hermes agent](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md).

### `GET /v1/models`

Список профилей Helix в формате OpenAI models (`id` = имя профиля).

```bash
curl -sS -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8000/v1/models
```

### `GET /v1/capabilities`

Feature flags и карта эндпоинтов для Hermes-клиентов.

### `GET /v1/toolsets`

Инструменты агента, сгруппированные в один toolset `"core"` для определённого профиля.

### `GET /v1/skills`

Список навыков: `[{name, description, category}]`.

### `POST /v1/responses`

Создать сохранённый response (Responses API). Требуется право `read`.

**Тело (`ResponsesCreateRequest`):**

| Поле | Тип | Описание |
|------|-----|----------|
| `model` | string | Имя профиля (по умолчанию `helix`) |
| `input` | string или array | Ввод пользователя |
| `instructions` | string? | Системные инструкции |
| `store` | bool | Сохранить в SQLite store (по умолчанию true) |
| `previous_response_id` | string? | Цепочка responses |
| `conversation` | string? | Id разговора |

### `GET /v1/responses/{response_id}`

Получить сохранённый response.

### `DELETE /v1/responses/{response_id}`

Удалить сохранённый response.

### `POST /v1/runs`

Отправить асинхронный run агента. Требуется `execute` или `read`.

**Тело (`RunsCreateRequest`):** `model`, `input`, `session_id`, `instructions`, `conversation_history`, `previous_response_id`.

### `GET /v1/runs/{run_id}`

Опрос статуса run и вывода.

### `GET /v1/runs/{run_id}/events`

SSE-поток событий run до завершения.

### `POST /v1/runs/{run_id}/stop`

Запросить отмену.

### `POST /v1/runs/{run_id}/approval`

Human-in-the-loop approval.

**Тело:** `{"decision":"approve"|"reject", "comment": "…"}`

---

## Расширения агента (`/v1`)

Эндпоинты агента, специфичные для Helix (OpenAI chat, permissions, plans).

### `POST /v1/chat/completions`

OpenAI-совместимый chat. Требуется `read` на API key.

**Тело:** стандартный `ChatCompletionRequest` — `model`, `messages`, опционально `stream`, `conversation_id`.

```bash
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

Со streaming: `"stream": true` → SSE chunks.

### `GET /v1/conversations/{conversation_id}`

История разговора. Query: `limit` (по умолчанию 30).

### `GET /v1/tools`

Список инструментов, доступных агенту для определённого профиля.

### `POST /v1/search`

Поиск по памяти. Query-параметры: `query`, `top_k`.

### `POST /v1/permissions/grant`

Выдать разрешение на инструмент. Требуется `execute`. Параметры: `tool_name`, `risk_level`, `scope` (`session`|`permanent`).

### `GET /v1/permissions`

Список текущих выданных разрешений.

### `DELETE /v1/permissions/{grant_key}`

Отозвать разрешение. Query: `scope`.

### `POST /v1/confirmations/resolve`

Разрешить подтверждение рискованного действия из UI-флоу агента.

### `POST /v1/plan/review`

Разрешить ревью плана: `review_id`, `choice`, `feedback`.

### `GET /v1/plans`

Список планов. Query: `limit` (по умолчанию 20).

### `GET /v1/plans/{plan_id}`

Получить план по id.

---

## Сессии (`/api/sessions`)

Hermes session store для каждого профиля.

### `GET /api/sessions`

Список сессий. Query: `limit` (50), `offset` (0). Профиль через `X-Helix-Profile`.

### `POST /api/sessions`

Создать сессию. Тело: `{"title":"","profile":null}`.

### `GET /api/sessions/{session_id}`

Метаданные сессии.

### `PATCH /api/sessions/{session_id}`

Обновить `title`, `end_reason`.

### `DELETE /api/sessions/{session_id}`

Удалить сессию.

### `GET /api/sessions/{session_id}/messages`

Сообщения сессии. Query: `limit` (50).

### `POST /api/sessions/{session_id}/fork`

Форк сессии в новый id.

### `POST /api/sessions/{session_id}/chat`

Чат в контексте сессии. Тело: `{"input":"…","model":null}`. Требуется `read`.

### `POST /api/sessions/{session_id}/chat/stream`

То же, что chat, но SSE-поток.

---

## Cron-задачи (`/api/jobs`)

Запланированные задачи по профилю (gateway cron companion).

### `GET /api/jobs`

Список cron jobs для определённого профиля.

### `POST /api/jobs`

Создать job.

**Тело (`JobCreateRequest`):**

| Поле | Алиас Hermes | Описание |
|------|--------------|----------|
| `task` | `prompt` | Инструкция для агента |
| `cron_expression` | `schedule` | 5-field cron или фразы (`every day at 9`, `hourly`) |
| `name` | — | Отображаемое имя |
| `enabled` | — | Флаг активности |
| `notify_chat_id` | `delivery_target` | Telegram chat для уведомлений |
| `session_id` | — | Сессия для сводок запусков |
| `skills` | — | Предпочитаемые навыки для run |
| `model_override` | `provider_override` | Опциональная модель для job |

```bash
curl -sS -X POST http://127.0.0.1:8000/api/jobs \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"task":"Daily summary","cron_expression":"0 9 * * *","name":"morning"}'
```

### `GET /api/jobs/{job_id}`

Детали job.

### `PATCH /api/jobs/{job_id}`

Обновить любое из: `task`, `cron_expression`, `name`, `enabled`, `notify_chat_id`, `session_id`.

### `DELETE /api/jobs/{job_id}`

Удалить job и отменить in-flight run, если он выполняется.

### `POST /api/jobs/{job_id}/pause`

Отключить job (`enabled=false`).

### `POST /api/jobs/{job_id}/resume`

Включить job.

### `POST /api/jobs/{job_id}/run`

Запустить job немедленно (однократно).

---

## Управление: профили

Префикс `/api/helix/profiles`. API key gateway + доступ к профилю (см. [Аутентификация](#аутентификация)).

### `GET /api/helix/profiles`

**Аутентификация:** Admin

Список всех профилей с `name`, `protected`, `path`.

### `POST /api/helix/profiles`

**Аутентификация:** Admin

Создать профиль.

**Тело (`ProfileCreateRequest`):**

| Поле | По умолчанию | Описание |
|------|--------------|----------|
| `name` | обязательный | Id профиля |
| `inherit_global` | true | Копировать глобальный config |
| `with_access_key` | false | Сгенерировать ключ доступа `hp_…` |
| `workspace_jail` | false | Включить изоляцию workspace |

**Ответ:** `profile`, `access_key` (если создан), `protected`, `reload_required`.

### `GET /api/helix/profiles/{profile_id}`

Метаданные профиля: настройки jail, пути.

### `GET /api/helix/profiles/{profile_id}/status`

Агент загружен в registry, статус companions (Telegram, cron).

### `DELETE /api/helix/profiles/{profile_id}`

**Аутентификация:** Admin. Удалить директорию профиля.

### `POST /api/helix/profiles/{profile_id}/reload`

Перезагрузить агента + Telegram + cron для этого профиля.

### `GET /api/helix/profiles/{profile_id}/key/status`

Требуется ли для профиля ключ доступа.

### `POST /api/helix/profiles/{profile_id}/key/init`

Включить ключ доступа + workspace jail. Возвращает новый `hp_…` один раз.

### `POST /api/helix/profiles/{profile_id}/key/rotate`

**Тело:** `{"current_key":"hp_…"}`. Возвращает новый ключ один раз.

### `POST /api/helix/profiles/{profile_id}/key/disable`

**Аутентификация:** Admin. Снять защиту ключом доступа.

### `GET /api/helix/profiles/{profile_id}/jail`

Workspace jail: включён/путь.

### `POST /api/helix/profiles/{profile_id}/jail/enable`

**Тело:** опционально `{"path":"/allowed/root"}`.

### `POST /api/helix/profiles/{profile_id}/jail/disable`

Отключить workspace jail.

---

## Управление: модели

Префикс `/api/helix/profiles/{profile_id}/models`.

### `GET …/presets`

Каталог провайдеров (OpenRouter, Ollama и т.д.).

### `GET …/providers`

Настроенные провайдеры (API keys замаскированы).

### `POST …/providers`

Добавить провайдера из preset.

**Тело (`ProviderAddRequest`):** `preset_id`, опционально `name`, `api_key`, `host`, `port`, `skip_test`, `no_verify_ssl`.

### `DELETE …/providers/{provider_name}`

Удалить провайдера из config профиля.

### `POST …/providers/{provider_name}/test`

Проверить подключение и обнаружить модели.

### `GET …/agent-models`

Карта роль агента → конфигурация модели.

### `PATCH …/agent-models`

**Тело:** `{"agent_models":{…}}`.

### `GET …/fallbacks`

Упорядоченная цепочка fallback-провайдеров.

### `PATCH …/fallbacks`

**Тело:** `{"providers":["openrouter","ollama"]}`.

---

## Управление: навыки

Префикс `/api/helix/profiles/{profile_id}/skills`.

### `GET …/skills`

Список навыков. Query: `limit`, `agent` (фильтр по назначению).

### `GET …/skills/search`

Семантический поиск. Query: `q` (обязательный).

### `GET …/skills/{skill_name}`

Метаданные навыка и markdown-содержимое.

### `GET …/skills/assignments`

Навык → allowlists агентов.

### `PATCH …/skills/assignments`

**Тело:** `{"assignments":{"agent_name":["skill-a","skill-b"]}}`.

### `POST …/skills/seed-bundled`

Установить bundled skills. Query: `force` (bool).

---

## Управление: MCP

Префикс `/api/helix/profiles/{profile_id}/mcp`.

### `GET …/servers`

Все MCP servers + назначения.

### `POST …/servers`

**Тело (`McpServerCreateRequest`):** `name`, `transport` (`stdio`|`sse`), `command`, `args`, `url`, `env`, `risk_level`.

### `GET …/servers/{server_name}`

Конфигурация одного server (замаскирована).

### `DELETE …/servers/{server_name}`

Удалить server.

### `POST …/servers/{server_name}/test`

Подключиться и получить список удалённых инструментов.

### `GET …/assignments`

Соответствие агент → MCP server.

### `PATCH …/assignments`

**Тело:** `{"assignments":{"agent":["server-a"]}}`.

### `GET …/popular`

Кураторский список устанавливаемых MCP servers.

### `POST …/install`

**Тело (`McpInstallRequest`):** `popular_key` или `git_url`, опционально `params`.

---

## Управление: config и env

Префикс `/api/helix/profiles/{profile_id}`.

### `GET …/config`

`config.yaml` профиля (секреты замаскированы).

### `PATCH …/config`

**Тело:** `{"updates":{…}}` deep-merge в config профиля. Возвращает `reload_required`.

### `GET …/env`

Переменные `.env` профиля (замаскированы).

### `PATCH …/env`

**Тело:** `{"variables":{"KEY":"value"}}`.

---

## Управление: глобальные настройки

Префикс `/api/helix/global`. Требуется доступ к **Admin**-профилю.

### `POST /api/helix/global/init`

Создать шаблоны `~/.helix/global/config.yaml` и `.env`.

### `GET /api/helix/global/config`

Прочитать глобальный config (замаскирован).

### `PATCH /api/helix/global/config`

Патч глобального YAML.

### `GET /api/helix/global/env`

Прочитать глобальный `.env` (замаскирован).

### `PATCH /api/helix/global/env`

Патч глобальных переменных окружения.

---

## Управление: Telegram

Префикс `/api/helix/profiles/{profile_id}/telegram`. CLI-эквиваленты — в [TELEGRAM.md](TELEGRAM.md).

### `GET …/status`

Бот настроен, токен замаскирован, pending access requests, карта пользователей, companions.

### `POST …/setup`

**Тело:** `{"bot_token":"…","also_project_env":false}`. Проверка через Telegram `getMe`, сохранение `telegram.env`.

### `GET …/requests`

Список pending access requests + количество.

### `POST …/requests/{user_id}/approve`

**Аутентификация:** доступ к admin-профилю.

**Тело (`TelegramApproveRequest`):** одно из `profile`, `create_profile` или `set_admin:true`.

### `POST …/requests/{user_id}/reject`

**Аутентификация:** Admin. Отклонить pending request.

### `GET …/admin`

Telegram admin user id и сопоставленный профиль Helix.

### `DELETE …/admin`

**Аутентификация:** Admin. Сбросить Telegram admin.

### `GET …/map`

Соответствие user id → профиль Helix.

### `POST …/map`

**Тело:** `{"user_id":12345,"profile":"alice"}`.

### `DELETE …/map/{user_id}`

Удалить соответствие.

### `POST …/sync-menu`

Отправить меню команд бота в Telegram API.

---

## API чата сайта документации

Префикс `/v1/docs/chat`. Питает виджет сайта документации — **без инструментов агента**, только RAG по документации.

### `GET /v1/docs/chat/config`

**Аутентификация:** публичный

`{"enabled":true,"proxy_path":"/api/docs-chat",…}`

### `GET /v1/docs/chat/session`

**Аутентификация:** docs-chat token

Query: `client_id` (8–64 символа). Возвращает сохранённую историю чата посетителя.

### `DELETE /v1/docs/chat/session`

**Аутентификация:** docs-chat token

Очистить историю для `client_id`.

### `POST /v1/docs/chat`

**Аутентификация:** docs-chat token

**Тело:**

| Поле | Описание |
|------|----------|
| `message` | Вопрос (1–4000 символов) |
| `client_id` | Анонимный id посетителя |
| `lang` | `en` или `ru` |
| `page_slug` | Опционально текущая страница документации |
| `stream` | SSE при true (по умолчанию) |

Rate limit на `client_id` (`HELIX_DOCS_CHAT_RATE_LIMIT_RPM`).

---

## Архитектура multi-profile

Один процесс uvicorn обслуживает **N профилей** через `ProfileAgentRegistry`:

- Агенты lazy-load при первом запросе
- `CompanionManager` запускает Telegram polling + cron для каждого профиля
- `POST …/reload` перезапускает агента и companions одного профиля без перезапуска gateway
- Host profile задаётся при старте (`HELIX_PROFILE`)

Хранилища: `ResponsesStore` (SQLite), `RunsStore` (memory), `SessionsStore` (memory).

---

## Замечания по безопасности

- Используйте **TLS** за reverse proxy в production; по умолчанию bind `127.0.0.1`
- Установите `HELIX_API_KEY_PEPPER` в production (обязательно при `HELIX_ENV=production`)
- Admin-маршруты всегда требуют право admin
- Security headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`
- CORS: `HELIX_CORS_ORIGINS` (через запятую)

См. также: [SECURITY.md](SECURITY.md), [DEPLOYMENT.md](DEPLOYMENT.md), [PROFILES.md](PROFILES.md), [TELEGRAM.md](TELEGRAM.md).