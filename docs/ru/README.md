# Документация Holix (русский)

Английская версия — основная для точности: [../en/README.md](../en/README.md).

**Установка:** `uv tool install Holix` или [INSTALLATION.md](INSTALLATION.md) (путь **uv** / **Docker**).

> **Канал:** [Telegram @helix_agent](https://t.me/helix_agent)

---

## С чего начать

| Шаг | Документ |
|-----|----------|
| 0. **Обзор продукта** (для пользователей) | [HOLIX_OVERVIEW.md](HOLIX_OVERVIEW.md) |
| 1. Установка | [INSTALLATION.md](INSTALLATION.md) |
| 2. Первый запуск | [START_HERE.md](START_HERE.md) |
| 3. Маршрут обучения | [USER_GUIDE.md](USER_GUIDE.md) |
| Локальная IDE (один пользователь) | [Holix Studio CE](https://github.com/javded-itres/holix-studio-ce) |

---

## Карта документации

### Установка и конфигурация

- [INSTALLATION.md](INSTALLATION.md) — путь A: uv · путь B: Docker
- [START_HERE.md](START_HERE.md) — чеклист + шпаргалка
- [CONFIGURATION.md](CONFIGURATION.md) · [MODELS.md](MODELS.md) · [PROFILES.md](PROFILES.md) · [PROFILE_ENCRYPTION.md](PROFILE_ENCRYPTION.md)

### Работа с агентом

- [TUI.md](TUI.md) — очередь, todos, живые процессы, копирование
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) · [EXECUTION_MODES.md](EXECUTION_MODES.md)
- [CODE_MODE.md](CODE_MODE.md) — `run_code` / `tools_presentation`
- [CLI.md](CLI.md) · [HUB.md](HUB.md) · [BROWSER_TOOLS.md](BROWSER_TOOLS.md) · [TOOLS.md](TOOLS.md) — `lsp`, `tool_search`, `send_chat_files`, `self_diagnose`, `research_site_pages`
- [MCP.md](MCP.md) · [MEMORY.md](MEMORY.md) — Chroma или pgvector

### Агенты и автоматизация

- [SUBAGENTS.md](SUBAGENTS.md) — типы (TUI + Telegram/MAX), spawn, **supervisor**
- [ACP.md](ACP.md) — внешний coding-агент (`run_acp_agent`)
- [LAUNCH.md](LAUNCH.md) · [CRON.md](CRON.md)
- [en/SUBAGENT_SUPERVISOR.md](../en/SUBAGENT_SUPERVISOR.md) — дизайн supervisor

### Интеграции и API

- [TELEGRAM.md](TELEGRAM.md) · [MAX.md](MAX.md)
- [GATEWAY.md](GATEWAY.md) · [GATEWAY_API.md](GATEWAY_API.md)
- [Holix Studio CE](https://github.com/javded-itres/holix-studio-ce) — одноместная IDE на своей машине (витрина + установщик Holix)
- [Holix Studio Cloud](https://holix-studio.ru) — команды и облачная Studio

### Экосистема расширений

- [holix-sdk](https://github.com/javded-itres/holix-sdk) — отдельный пакет (PyPI: `holix-sdk`)
- [EXTENSIONS.md](EXTENSIONS.md) — создание расширений (пошагово, копия в репозитории holix-sdk)
- [BUILD_WITHOUT_HOLIX.md](../en/BUILD_WITHOUT_HOLIX.md) · [EXTENSION_GATEWAY.md](../en/EXTENSION_GATEWAY.md)

### Безопасность и эксплуатация

- [SECURITY.md](SECURITY.md) · [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md)
- [DEPLOYMENT.md](DEPLOYMENT.md) · [LOGS.md](LOGS.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

### Внутренности

- [ARCHITECTURE.md](ARCHITECTURE.md) · [CHANGELOG.md](../CHANGELOG.md) · [LICENSING_STRATEGY.md](LICENSING_STRATEGY.md)
- [SDD.md](SDD.md) — Spec-Driven Development (tools, slash, Studio)
- [SDD_STUDIO_PLAN.md](SDD_STUDIO_PLAN.md) — план SDD в Studio (модель OpenSpec)

---

**Сайт:** [holix-agent.ru/docs](https://holix-agent.ru/docs)
