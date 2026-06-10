# Безопасность

## Чеклист production

1. `HELIX_ENV=production`
2. `HELIX_REQUIRE_AUTH=true` (в production принудительно)
3. `HELIX_API_KEY_PEPPER` — длинный случайный секрет
4. `HELIX_CORS_ORIGINS` — явные origin (не `*`)
5. `HELIX_GATEWAY_HOST=127.0.0.1` за reverse proxy с TLS
6. `HELIX_TELEGRAM_ALLOWED_USERS` при использовании Telegram
7. `HELIX_ENABLE_CODE_EXECUTOR=false` если не нужен
8. `HELIX_TERMINAL_COMMAND_WHITELIST=true`

## Web TUI (`helix tui --web`)

Браузерный UI — полноценный агент (терминал, файлы, MCP). Считайте это root на вашей машине.

| Bind | Требования |
|------|------------|
| `127.0.0.1` (по умолчанию) | `--token`, `HELIX_TUI_WEB_TOKEN` или эфемерный `--generate-token` (по умолчанию) |
| `0.0.0.0` / LAN | `--allow-lan` **и** явный `--token` / env (автотокен не создаётся) |
| `HELIX_ENV=production` | Явный token всегда |

- Не выставляйте порт 8787 в интернет без TLS и reverse proxy.
- Меняйте token после передачи LAN-URL.

## API keys

- Хранение: HMAC-SHA256 с pepper
- `/admin/*` всегда требуют permission `admin`
- Создание: `POST /admin/api-keys` с admin key

## Секреты в профиле

В `~/.helix/profiles/<name>/config.yaml`:

```yaml
api_key: ${OPENAI_API_KEY}
```

Не коммитьте реальные ключи в git.

## Инструменты

- **Terminal**: whitelist, блокировка опасных паттернов, подтверждения — подробно: [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md). Быстрая настройка:
  ```bash
  helix -p dev profile whitelist enable
  helix -p dev profile whitelist add "docker, make"
  helix -p dev profile whitelist list
  ```
- **Python executor**: `HELIX_ENABLE_CODE_EXECUTOR=false` в production

## Аудит

```bash
helix doctor
helix doctor --fix
```