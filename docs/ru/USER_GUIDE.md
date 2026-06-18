# Holix — маршрут обучения

Навигация по документации. На каждую тему — **одна каноническая страница**; здесь только ссылки.

> Пакет **`Holix`** на PyPI; команда **`holix`**.  
> Не в боковом меню сайта — открывайте из [README](README.md) или [START_HERE](START_HERE.md).

---

## 1. Установка и первый запуск

| Шаг | Документ |
|-----|----------|
| Локально (uv) или Docker | [INSTALLATION.md](INSTALLATION.md) |
| Чеклист после установки | [START_HERE.md](START_HERE.md) |
| Шпаргалка команд | [START_HERE.md § Шпаргалка](START_HERE.md#шпаргалка-команд) |
| Диагностика | [DOCTOR.md](DOCTOR.md) |

---

## 2. Конфигурация и профили

| Тема | Документ |
|------|----------|
| `.env`, слои YAML | [CONFIGURATION.md](CONFIGURATION.md) |
| Модели и провайдеры | [MODELS.md](MODELS.md) |
| Долговременная память | [MEMORY.md](MEMORY.md) |
| Профили, SOUL/USER, jail, ключи | [PROFILES.md](PROFILES.md) |
| Шифрование | [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md) |
| Режимы (ReAct, Plan, Hybrid) | [EXECUTION_MODES.md](EXECUTION_MODES.md) |

---

## 3. Интерфейсы

| Интерфейс | Документ |
|-----------|----------|
| TUI | [TUI.md](TUI.md) |
| Слэш-команды | [SLASH_COMMANDS.md](SLASH_COMMANDS.md) |
| Справочник CLI | [CLI.md](CLI.md) |
| Hub | [HUB.md](HUB.md) |
| MCP | [MCP.md](MCP.md) |

---

## 4. Агенты и автоматизация

| Тема | Документ |
|------|----------|
| Субагенты | [SUBAGENTS.md](SUBAGENTS.md) |
| Внешние CLI (`holix launch`) | [LAUNCH.md](LAUNCH.md) |
| Cron | [CRON.md](CRON.md) |
| Браузер | [BROWSER_TOOLS.md](BROWSER_TOOLS.md) |

---

## 5. Интеграции

| Канал | Документ |
|-------|----------|
| Telegram | [TELEGRAM.md](TELEGRAM.md) |
| MAX | [MAX.md](MAX.md) |
| Gateway | [GATEWAY.md](GATEWAY.md) |
| API | [GATEWAY_API.md](GATEWAY_API.md) |

---

## 6. Безопасность и эксплуатация

| Тема | Документ |
|------|----------|
| Production checklist | [SECURITY.md](SECURITY.md) |
| Терминал и whitelist | [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md) |
| Docker / systemd / TLS | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Логи | [LOGS.md](LOGS.md) |
| Проблемы | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |

---

## 7. Внутренности

| Тема | Документ |
|------|----------|
| Архитектура | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Changelog | [../CHANGELOG.md](../CHANGELOG.md) |
| PyPI | [PYPI.md](PYPI.md) |

---

## Рекомендуемый порядок

1. [INSTALLATION.md](INSTALLATION.md) → [START_HERE.md](START_HERE.md)  
2. [CONFIGURATION.md](CONFIGURATION.md) → [PROFILES.md](PROFILES.md)  
3. [TUI.md](TUI.md) + [SLASH_COMMANDS.md](SLASH_COMMANDS.md)  
4. [GATEWAY.md](GATEWAY.md) или [TELEGRAM.md](TELEGRAM.md) / [MAX.md](MAX.md)  
5. [SECURITY.md](SECURITY.md) перед production