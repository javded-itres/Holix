# Документация Holix (русский)

Английская версия — основная: [../en/README.md](../en/README.md).

**Установка с PyPI:** `pipx install HelixAgentAi` — [pypi.org/project/HelixAgentAi](https://pypi.org/project/HelixAgentAi/)

> **Следите за развитием:** подпишитесь на [Telegram-канал @holix_agent](https://t.me/holix_agent) — релизы, планы и новости проекта.

## С чего начать

1. [INSTALLATION.md](INSTALLATION.md) — установка с PyPI, **Windows**, extras, обновления
2. [START_HERE.md](START_HERE.md) — первый запуск
3. [QUICKSTART.md](QUICKSTART.md) — минимум команд
4. [CONFIGURATION.md](CONFIGURATION.md) — `.env`, профили
5. [PROFILES.md](PROFILES.md) — **изолированные профили, SOUL/USER, ключи доступа, несколько пользователей, workspace jail**

## Интерфейсы

- [CLI.md](CLI.md) — **справочник команд `holix`**
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — **слэш-команды `/`**
- [EXECUTION_MODES.md](EXECUTION_MODES.md) — **ReAct, Plan, Hybrid, Auto** — как работают режимы и примеры промптов
- [TUI.md](TUI.md) — `holix tui`
- [HUB.md](HUB.md) — каталоги навыков
- [GATEWAY.md](GATEWAY.md) — API gateway
- [GATEWAY_API.md](GATEWAY_API.md) — **полный справочник API — каждый эндпоинт задокументирован** (auth, `/api/holix/`, SaaS curl)
- [TELEGRAM.md](TELEGRAM.md) — Telegram
- [TELEGRAM_MULTI_PROFILE.md](TELEGRAM_MULTI_PROFILE.md) — один бот / несколько ботов, access requests, ручной `map`
- [BROWSER_TOOLS.md](BROWSER_TOOLS.md) — Playwright

## Эксплуатация

- [LOGS.md](LOGS.md) — `holix logs`, ротация, debug
- [DOCTOR.md](DOCTOR.md)
- [SECURITY.md](SECURITY.md)
- [TERMINAL_SECURITY.md](TERMINAL_SECURITY.md) — whitelist терминала, запрещённые команды, подтверждения
- [DEPLOYMENT.md](DEPLOYMENT.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)