# Безопасность

## Чеклист production

1. `HOLIX_ENV=production`
2. `HOLIX_REQUIRE_AUTH=true` (в production принудительно)
3. `HOLIX_API_KEY_PEPPER` — длинный случайный секрет
4. `HOLIX_CORS_ORIGINS` — явные origin (не `*`)
5. `HOLIX_GATEWAY_HOST=127.0.0.1` за reverse proxy с TLS
6. Telegram: `HOLIX_TELEGRAM_ACCESS_REQUESTS=true` (по умолчанию после `telegram setup`) или `HOLIX_TELEGRAM_ALLOWED_USERS` для личного бота; в production — именованные профили (`-p shared`), не `default`
7. `HOLIX_ENABLE_CODE_EXECUTOR=false` если не нужен
8. `HOLIX_TERMINAL_COMMAND_WHITELIST=true`

## Web TUI (`holix tui --web`)

Браузерный UI — полноценный агент (терминал, файлы, MCP). Считайте это root на вашей машине.

| Bind | Требования |
|------|------------|
| `127.0.0.1` (по умолчанию) | `--token`, `HOLIX_TUI_WEB_TOKEN` или эфемерный `--generate-token` (по умолчанию) |
| `0.0.0.0` / LAN | `--allow-lan` **и** явный `--token` / env (автотокен не создаётся) |
| `HOLIX_ENV=production` | Явный token всегда |

- Не выставляйте порт 8787 в интернет без TLS и reverse proxy.
- Меняйте token после передачи LAN-URL.

## API keys

- Хранение: HMAC-SHA256 с pepper
- `/admin/*` всегда требуют permission `admin`
- Создание: `POST /admin/api-keys` с admin key (нет CLI-команды `holix` для `hx_` — используйте curl или Swagger `/docs`)

### Двухслойная аутентификация gateway

Gateway использует **два независимых credential**:

| Слой | Ключ | Префикс | Назначение |
|------|------|---------|------------|
| 1 — API key gateway | `Authorization: Bearer …` или `X-API-Key` | `hx_…` | Аутентификация всех защищённых HTTP-маршрутов (chat, Hermes, management) |
| 2 — Ключ доступа к профилю | `X-Holix-Profile-Key` | `hp_…` | Авторизация `/api/holix/*` management для конкретного профиля |

**Слой 1** обязателен при `HOLIX_REQUIRE_AUTH=true` (кроме `/health`, `/v1/health`). Ключи `hx_` создаются через `POST /admin/api-keys`.

**Слой 2** только для `/api/holix/*`. Владелец профиля отправляет свой `hp_…` для управления своим профилем. Админы gateway обходят слой 2 ключом API с правом `admin` или master-ключом admin-профиля (`HOLIX_TELEGRAM_ADMIN_PROFILE`, по умолчанию `admin`). Ключи `hp_` — через `holix profile key init`, не через admin API gateway.

Chat и Hermes (`/v1/chat/completions`, `/v1/models` и т.д.) требуют **только слой 1**. Роутинг профиля — `X-Holix-Profile` или поле `model`, не `hp_`.

Таблицы: [GATEWAY_API.md](GATEWAY_API.md#authentication).

### Токен docs-chat (отдельная поверхность)

При запуске сайта документации с `--with-docs` и `HOLIX_DOCS_CHAT_ENABLED=1` встроенный ассистент использует **`HOLIX_DOCS_CHAT_TOKEN`** — отдельный секрет для `/v1/docs/chat` и прокси docs-server (`/api/docs-chat`).

Это **не** API key gateway (`hx_`) и **не** ключ профиля (`hp_`). Токен только на стороне сервера (прокси хранит его; браузер не видит). Ротируйте независимо от ключей gateway.

## Секреты в профиле

В `~/.holix/profiles/<name>/config.yaml`:

```yaml
api_key: ${OPENAI_API_KEY}
```

Не коммитьте реальные ключи в git.

## Инструменты

- **Terminal**: whitelist, блокировка опасных паттернов, подтверждения — подробно: [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md). Быстрая настройка:
  ```bash
  holix -p dev profile whitelist enable
  holix -p dev profile whitelist add "docker, make"
  holix -p dev profile whitelist list
  ```
- **Python executor**: `HOLIX_ENABLE_CODE_EXECUTOR=false` в production

## Аудит

```bash
holix doctor
holix doctor --fix
```