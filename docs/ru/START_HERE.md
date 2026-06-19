# Первый запуск

Чеклист после [INSTALLATION.md](INSTALLATION.md). Предполагается, что `holix` в PATH (путь A) или запущен Docker (путь B).

## 1. Проверка установки

```bash
holix version
holix doctor
holix doctor --fix
```

Docker:

```bash
docker compose ps
docker compose exec holix holix doctor
```

## 2. Первичная настройка

При **первом диалоге** в новом профиле Holix запускает онбординг (`INIT.md`): представьтесь, задайте личность агента (`SOUL.md`), предпочтения (`USER.md`). См. [PROFILES.md](PROFILES.md#agent-identity-soul-init-user).

Если bootstrap не запускался:

```bash
holix bootstrap
holix models setup
holix models list
holix config show
```

## 3. Выбор интерфейса

| Интерфейс | Команда | Когда |
|-----------|---------|-------|
| TUI (рекомендуется) | `holix tui` | Ежедневная работа, инструменты, hub, MCP |
| Чат в терминале | `holix chat-command` | Лёгкий REPL |
| Один запрос | `holix run "…"` | Скрипты |
| HTTP API | `holix gateway start` | Приложения, OpenAI-клиенты |
| Telegram | `holix -p shared telegram setup` | Мобильный доступ — [TELEGRAM.md](TELEGRAM.md) |
| MAX | `holix max setup` | [MAX.md](MAX.md) |

Слэш-команды: **`/help`** — [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

## 4. Опциональные возможности

Extras — [INSTALLATION.md](INSTALLATION.md):

```bash
uv tool install "Holix[all]"
holix -p shared telegram setup
holix hub browse
holix mcp setup
playwright install chromium
```

## 5. Production

```bash
export HOLIX_ENV=production
export HOLIX_REQUIRE_AUTH=true
export HOLIX_API_KEY_PEPPER=$(openssl rand -hex 32)
holix gateway start
```

[SECURITY.md](SECURITY.md), [DEPLOYMENT.md](DEPLOYMENT.md).

## Шпаргалка команд

```bash
holix doctor
holix models setup
holix run "Привет"
holix tui
holix gateway start
holix gateway status
holix cron list
holix launch setup
holix logs -l error
holix hub browse
holix mcp setup
holix update --channel pypi
```

Починка: `holix doctor --fix`

## Дальше

| Тема | Документ |
|------|----------|
| Конфигурация | [CONFIGURATION.md](CONFIGURATION.md) |
| Профили | [PROFILES.md](PROFILES.md) |
| CLI | [CLI.md](CLI.md) |
| Cron | [CRON.md](CRON.md) |
| Логи | [LOGS.md](LOGS.md) |
| Проблемы | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Полный маршрут обучения | [USER_GUIDE.md](USER_GUIDE.md) |