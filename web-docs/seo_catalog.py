"""Curated SEO titles, descriptions, and keywords for holix-agent.ru pages."""

from __future__ import annotations

# slug → {lang: {title, description, keywords}}
# Titles: 50–60 chars where possible. Descriptions: 140–160 chars for SERP snippets.

SEO_VIEWS: dict[str, dict[str, dict[str, str]]] = {
    "home": {
        "ru": {
            "title": "Holix — AI-агент с памятью, MCP и Telegram · Российская разработка",
            "description": (
                "Holix — российский самообучающийся AI-агент: долговременная память, навыки, "
                "MCP, CLI, TUI, API gateway и Telegram. Open source, деплой на своей инфраструктуре с Ollama и LiteLLM."
            ),
            "keywords": (
                "Holix AI агент, самообучающийся агент, российское ПО, LLM агент, Ollama, LiteLLM, "
                "MCP, Telegram бот, API gateway, open source AI"
            ),
        },
        "en": {
            "title": "Holix — Self-Improving AI Agent with Memory, MCP & Telegram",
            "description": (
                "Holix is an open-source self-improving AI agent: persistent memory, skills, MCP, CLI, TUI, "
                "API gateway, and Telegram. Deploy on-prem with Ollama, LiteLLM, or cloud LLMs."
            ),
            "keywords": (
                "Holix AI agent, self-improving agent, LLM agent, Ollama, LiteLLM, MCP, "
                "Telegram bot, API gateway, open source AI, Russian software"
            ),
        },
    },
    "docs-hub": {
        "ru": {
            "title": "Документация Holix — установка, CLI, профили, gateway, Telegram",
            "description": (
                "Полная документация Holix: установка с PyPI, первый запуск, конфигурация профилей, "
                "справочник CLI, TUI, API gateway, Telegram-бот, деплой в Docker и systemd."
            ),
            "keywords": (
                "документация Holix, Holix установка, Holix CLI, профили Holix, gateway API, "
                "Telegram бот Holix, руководство пользователя"
            ),
        },
        "en": {
            "title": "Holix Documentation — Install, CLI, Profiles, Gateway, Telegram",
            "description": (
                "Complete Holix docs: PyPI install, quickstart, profile configuration, CLI reference, "
                "TUI, API gateway, Telegram bot, Docker and systemd deployment guides."
            ),
            "keywords": (
                "Holix documentation, Holix install guide, Holix CLI, Holix profiles, "
                "API gateway, Telegram bot, user guide"
            ),
        },
    },
}

SEO_PAGES: dict[str, dict[str, dict[str, str]]] = {
    "readme": {
        "ru": {
            "title": "Обзор Holix — возможности AI-агента и структура документации",
            "description": (
                "Обзор Holix: самообучающийся AI-агент с памятью, навыками, MCP, CLI, TUI, gateway и Telegram. "
                "Карта документации для быстрого старта и углублённой настройки."
            ),
            "keywords": "Holix обзор, AI агент возможности, документация Holix, HolixAgentAi, PyPI",
        },
        "en": {
            "title": "Holix Overview — AI Agent Features & Documentation Map",
            "description": (
                "Overview of Holix: self-improving AI agent with memory, skills, MCP, CLI, TUI, gateway, and Telegram. "
                "Documentation map for quickstart and advanced setup."
            ),
            "keywords": "Holix overview, AI agent features, Holix documentation, HolixAgentAi, PyPI",
        },
    },
    "installation": {
        "ru": {
            "title": "Установка Holix — PyPI, pipx, Python 3.12, Docker",
            "description": (
                "Как установить Holix с PyPI (HolixAgentAi): pipx, venv, Python 3.12+, опциональные extras "
                "(Telegram, браузер, голос). Обновление, удаление и решение проблем установки."
            ),
            "keywords": "установка Holix, pipx install HelixAgentAi, PyPI, Python 3.12, Holix Docker",
        },
        "en": {
            "title": "Install Holix — PyPI, pipx, Python 3.12, Docker",
            "description": (
                "How to install Holix from PyPI (HolixAgentAi): pipx, venv, Python 3.12+, optional extras "
                "(Telegram, browser, voice). Updates, uninstall, and install troubleshooting."
            ),
            "keywords": "install Holix, pipx install HelixAgentAi, PyPI, Python 3.12, Holix Docker",
        },
    },
    "start-here": {
        "ru": {
            "title": "Первый запуск Holix — чеклист настройки за 5 шагов",
            "description": (
                "Чеклист первого запуска Holix: установка, holix doctor, настройка моделей, выбор интерфейса "
                "(TUI, chat, gateway) и опциональные функции Telegram и браузера."
            ),
            "keywords": "первый запуск Holix, holix doctor, настройка моделей, holix tui, быстрый старт",
        },
        "en": {
            "title": "Start Here — Holix First-Run Checklist in 5 Steps",
            "description": (
                "Holix first-run checklist: install, holix doctor, configure models, pick an interface "
                "(TUI, chat, gateway), and optional Telegram and browser features."
            ),
            "keywords": "Holix start here, holix doctor, configure models, holix tui, first run",
        },
    },
    "quickstart": {
        "ru": {
            "title": "Быстрый старт Holix — минимальные команды для запуска",
            "description": (
                "Минимальный быстрый старт Holix: pipx install HelixAgentAi, holix doctor, holix models setup, "
                "holix tui. Краткий список команд для немедленного начала работы с агентом."
            ),
            "keywords": "Holix быстрый старт, holix tui, holix models setup, минимальные команды",
        },
        "en": {
            "title": "Holix Quickstart — Minimal Commands to Run the Agent",
            "description": (
                "Minimal Holix quickstart: pipx install HelixAgentAi, holix doctor, holix models setup, "
                "holix tui. Short command list to start using the agent immediately."
            ),
            "keywords": "Holix quickstart, holix tui, holix models setup, minimal commands",
        },
    },
    "configuration": {
        "ru": {
            "title": "Конфигурация Holix — профили, .env, модели и MCP",
            "description": (
                "Конфигурация Holix: слои настроек, profiles/<name>/.env, config.yaml, провайдеры LLM "
                "(Ollama, LiteLLM, OpenRouter), MCP-серверы, Hub и секреты ${ENV:VAR}."
            ),
            "keywords": "конфигурация Holix, holix profile env, Ollama LiteLLM, MCP серверы, config.yaml",
        },
        "en": {
            "title": "Holix Configuration — Profiles, .env, Models & MCP",
            "description": (
                "Holix configuration: settings layers, profiles/<name>/.env, config.yaml, LLM providers "
                "(Ollama, LiteLLM, OpenRouter), MCP servers, Hub, and ${ENV:VAR} secrets."
            ),
            "keywords": "Holix configuration, holix profile env, Ollama LiteLLM, MCP servers, config.yaml",
        },
    },
    "profiles": {
        "ru": {
            "title": "Профили Holix — изоляция пользователей, ключи доступа, workspace jail",
            "description": (
                "Изоляция профилей Holix: отдельные .env, gateway, Telegram-бот и память на пользователя. "
                "Опциональные ключи доступа и workspace jail для ограничения файловых операций."
            ),
            "keywords": "Holix профили, изоляция профилей, workspace jail, ключ доступа профиля, multi-user",
        },
        "en": {
            "title": "Holix Profiles — User Isolation, Access Keys & Workspace Jail",
            "description": (
                "Holix profile isolation: separate .env, gateway, Telegram bot, and memory per user. "
                "Optional access keys and workspace jail to restrict file and terminal tools."
            ),
            "keywords": "Holix profiles, profile isolation, workspace jail, profile access key, multi-user",
        },
    },
    "cli": {
        "ru": {
            "title": "Справочник CLI Holix — все команды holix",
            "description": (
                "Полный справочник CLI Holix: chat, tui, gateway, models, telegram, profile, mcp, hub, "
                "cron, logs, doctor. Опции -p profile, примеры и типовые сценарии использования."
            ),
            "keywords": "Holix CLI, holix команды, holix gateway, holix models, holix telegram, справочник",
        },
        "en": {
            "title": "Holix CLI Reference — All holix Commands",
            "description": (
                "Complete Holix CLI reference: chat, tui, gateway, models, telegram, profile, mcp, hub, "
                "cron, logs, doctor. -p profile option, examples, and common workflows."
            ),
            "keywords": "Holix CLI, holix commands, holix gateway, holix models, holix telegram, reference",
        },
    },
    "execution-modes": {
        "ru": {
            "title": "Режимы работы Holix — ReAct, Plan, Hybrid, Auto с примерами",
            "description": (
                "Режимы Holix: ReAct, Plan & Execute, Hybrid и Auto. Как переключать /mode, "
                "согласование плана, подтверждения инструментов и примеры промптов для каждого режима."
            ),
            "keywords": (
                "Holix режимы, ReAct, plan_and_execute, hybrid, auto mode, /mode, "
                "промпты Holix, согласование плана"
            ),
        },
        "en": {
            "title": "Holix Execution Modes — ReAct, Plan, Hybrid, Auto with Prompts",
            "description": (
                "Holix execution modes: ReAct, Plan & Execute, Hybrid, and Auto. How to switch with /mode, "
                "plan approval, tool confirmations, and prompt examples for each mode."
            ),
            "keywords": (
                "Holix execution modes, ReAct, plan_and_execute, hybrid, auto mode, /mode, "
                "Holix prompts, plan review"
            ),
        },
    },
    "slash-commands": {
        "ru": {
            "title": "Слэш-команды Holix — /models, /skills, /mcp в TUI и Telegram",
            "description": (
                "Слэш-команды Holix в TUI и Telegram: /models, /profile, /skills, /mcp, /hub, /compress, "
                "/sessions. Управление сессией, моделями и инструментами без обращения к LLM."
            ),
            "keywords": "Holix слэш-команды, /models, /skills, TUI команды, Telegram команды Holix",
        },
        "en": {
            "title": "Holix Slash Commands — /models, /skills, /mcp in TUI & Telegram",
            "description": (
                "Holix slash commands in TUI and Telegram: /models, /profile, /skills, /mcp, /hub, /compress, "
                "/sessions. Control session, models, and tools without prompting the LLM."
            ),
            "keywords": "Holix slash commands, /models, /skills, TUI commands, Telegram commands",
        },
    },
    "tui": {
        "ru": {
            "title": "TUI Holix — терминальный интерфейс агента и веб-режим",
            "description": (
                "Holix TUI: полноэкранный терминальный интерфейс с инструментами, Hub, MCP, копированием "
                "и веб-режимом (holix tui --web). Ежедневная работа с агентом в консоли."
            ),
            "keywords": "Holix TUI, holix tui --web, терминальный AI агент, textual UI, консольный агент",
        },
        "en": {
            "title": "Holix TUI — Terminal UI, Tools, Hub & Web Mode",
            "description": (
                "Holix TUI: full-screen terminal interface with tools, Hub, MCP, copy support, "
                "and web mode (holix tui --web). Daily agent workflow in the console."
            ),
            "keywords": "Holix TUI, holix tui --web, terminal AI agent, textual UI, console agent",
        },
    },
    "hub": {
        "ru": {
            "title": "Hub и навыки Holix — каталоги skills, MCP и ClawHub",
            "description": (
                "Holix Hub: установка навыков и MCP из ClawHub, HermesHub, Claude plugins. "
                "holix hub search/install, skill assignments и автообновление каталогов."
            ),
            "keywords": "Holix Hub, holix skills, ClawHub, MCP install, навыки агента, holix hub install",
        },
        "en": {
            "title": "Holix Hub & Skills — Skill Catalogs, MCP & ClawHub",
            "description": (
                "Holix Hub: install skills and MCP from ClawHub, HermesHub, Claude plugins. "
                "holix hub search/install, skill assignments, and catalog auto-updates."
            ),
            "keywords": "Holix Hub, holix skills, ClawHub, MCP install, agent skills, holix hub install",
        },
    },
    "gateway": {
        "ru": {
            "title": "API Gateway Holix — OpenAI-совместимый HTTP API",
            "description": (
                "Holix API Gateway: OpenAI-совместимый REST API, holix gateway start/stop, аутентификация, "
                "Prometheus metrics, cron и Telegram как companion-процессы. Настройка портов и профилей."
            ),
            "keywords": "Holix gateway, API gateway, OpenAI compatible API, holix gateway start, Prometheus",
        },
        "en": {
            "title": "Holix API Gateway — OpenAI-Compatible HTTP API",
            "description": (
                "Holix API Gateway: OpenAI-compatible REST API, holix gateway start/stop, authentication, "
                "Prometheus metrics, cron and Telegram companions. Per-profile ports and setup."
            ),
            "keywords": "Holix gateway, API gateway, OpenAI compatible API, holix gateway start, Prometheus",
        },
    },
    "gateway-api": {
        "ru": {
            "title": "Полный справочник Holix Gateway API — все эндпоинты",
            "description": (
                "Полное описание Holix Gateway API: 110+ эндпоинтов Hermes, chat, sessions, jobs, "
                "/api/holix/ management, admin, metrics, docs-chat. Аутентификация, Swagger Authorize, curl-примеры."
            ),
            "keywords": (
                "Holix Gateway API, справочник API, Hermes API, Holix Management API, /api/helix, "
                "OpenAPI Swagger, Telegram admin API, REST API документация"
            ),
        },
        "en": {
            "title": "Complete Holix Gateway API Reference — Every Endpoint",
            "description": (
                "Full Holix Gateway API docs: 110+ endpoints for Hermes, chat, sessions, jobs, "
                "/api/holix/ management, admin, metrics, docs-chat. Auth, Swagger Authorize, curl examples."
            ),
            "keywords": (
                "Holix Gateway API, complete API reference, Hermes API, Holix Management API, /api/helix, "
                "OpenAPI Swagger, Telegram admin API, REST API documentation"
            ),
        },
    },
    "telegram": {
        "ru": {
            "title": "Telegram-бот Holix — настройка, голос, slash-команды",
            "description": (
                "Telegram-интеграция Holix: holix telegram setup, отдельный бот на профиль, allowlist, "
                "голосовые сообщения (Whisper), inline-подтверждения и канал @holix_agent с новостями."
            ),
            "keywords": "Holix Telegram, holix telegram setup, Telegram бот AI, голосовые сообщения Whisper",
        },
        "en": {
            "title": "Holix Telegram Bot — Setup, Voice Notes & Slash Commands",
            "description": (
                "Holix Telegram integration: holix telegram setup, per-profile bot, allowlist, "
                "voice messages (Whisper), inline approvals, and @holix_agent channel for news."
            ),
            "keywords": "Holix Telegram, holix telegram setup, Telegram AI bot, voice Whisper",
        },
    },
    "telegram-multi-profile": {
        "ru": {
            "title": "Telegram Holix — один бот, несколько изолированных профилей",
            "description": (
                "Как настроить Holix в Telegram для нескольких пользователей: отдельный бот на профиль "
                "или один бот с holix telegram map — привязка user id к профилю, jail и безопасность."
            ),
            "keywords": "Holix Telegram профили, holix telegram map, изоляция профилей, общий бот",
        },
        "en": {
            "title": "Holix Telegram — One Bot, Multiple Isolated Profiles",
            "description": (
                "Run Holix in Telegram for multiple users: one bot per profile or a shared bot with "
                "holix telegram map user id bindings, workspace jail, and security checklist."
            ),
            "keywords": "Holix Telegram profiles, holix telegram map, profile isolation, shared bot",
        },
    },
    "browser-tools": {
        "ru": {
            "title": "Браузерные инструменты Holix — Playwright автоматизация",
            "description": (
                "Браузерные инструменты Holix на Playwright: открытие страниц, клики, ввод текста, "
                "скриншоты. Безопасность URL, подтверждения и установка extra browser."
            ),
            "keywords": "Holix browser tools, Playwright, автоматизация браузера, holix browser extra",
        },
        "en": {
            "title": "Holix Browser Tools — Playwright Web Automation",
            "description": (
                "Holix browser tools with Playwright: open pages, click, type, screenshots. "
                "URL security policy, confirmations, and browser extra installation."
            ),
            "keywords": "Holix browser tools, Playwright, web automation, holix browser extra",
        },
    },
    "architecture": {
        "ru": {
            "title": "Архитектура Holix — runtime, DI, LangGraph, память",
            "description": (
                "Архитектура Holix: DI-контейнер, LangGraph execution, события, подагенты, SQLite + ChromaDB "
                "память, MCP и модульная структура CLI, gateway и интеграций."
            ),
            "keywords": "архитектура Holix, LangGraph, ChromaDB память, DI container, AI agent architecture",
        },
        "en": {
            "title": "Holix Architecture — Runtime, DI, LangGraph & Memory",
            "description": (
                "Holix architecture: DI container, LangGraph execution, events, subagents, SQLite + ChromaDB "
                "memory, MCP, and modular CLI, gateway, and integration layout."
            ),
            "keywords": "Holix architecture, LangGraph, ChromaDB memory, DI container, AI agent architecture",
        },
    },
    "security": {
        "ru": {
            "title": "Безопасность Holix — auth, whitelist, production checklist",
            "description": (
                "Безопасность Holix: API-ключи HMAC, gateway auth, whitelist терминала, подтверждения "
                "опасных операций, SSRF-защита браузера и чеклист для production-деплоя."
            ),
            "keywords": "Holix безопасность, API key, gateway auth, terminal whitelist, production security",
        },
        "en": {
            "title": "Holix Security — Auth, Whitelist & Production Checklist",
            "description": (
                "Holix security: HMAC API keys, gateway auth, terminal whitelist, risky-action confirmations, "
                "browser SSRF checks, and production deployment checklist."
            ),
            "keywords": "Holix security, API key, gateway auth, terminal whitelist, production security",
        },
    },
    "terminal-security": {
        "ru": {
            "title": "Безопасность команд Holix — whitelist, запреты и подтверждения",
            "description": (
                "Как Holix защищает run_terminal_command: whitelist по профилю, блокировка опасных "
                "паттернов, подтверждение /yes, workspace jail и примеры разрешённых и запрещённых команд."
            ),
            "keywords": (
                "Holix whitelist, безопасность терминала, run_terminal_command, "
                "HOLIX_TERMINAL_WHITELIST_EXTRA, подтверждение команд"
            ),
        },
        "en": {
            "title": "Holix Terminal Security — Whitelist, Blocks & Confirmations",
            "description": (
                "How Holix protects run_terminal_command: per-profile whitelist, dangerous pattern "
                "blocks, /yes confirmations, workspace jail, and allowed vs forbidden command examples."
            ),
            "keywords": (
                "Holix terminal whitelist, command safety, run_terminal_command, "
                "HOLIX_TERMINAL_WHITELIST_EXTRA, shell confirmation"
            ),
        },
    },
    "deployment": {
        "ru": {
            "title": "Деплой Holix — Docker, systemd, multi-profile production",
            "description": (
                "Деплой Holix в production: Docker, systemd holix-gateway@, несколько профилей на одном "
                "сервере, переменные окружения, docs-сайт и CI/CD рекомендации."
            ),
            "keywords": "деплой Holix, systemd holix-gateway, Docker Holix, production deployment, multi-profile",
        },
        "en": {
            "title": "Deploy Holix — Docker, systemd & Multi-Profile Production",
            "description": (
                "Deploy Holix in production: Docker, systemd holix-gateway@, multiple profiles on one "
                "server, environment variables, docs site, and CI/CD recommendations."
            ),
            "keywords": "deploy Holix, systemd holix-gateway, Docker Holix, production deployment",
        },
    },
    "doctor": {
        "ru": {
            "title": "Holix Doctor — диагностика и автоисправление конфигурации",
            "description": (
                "holix doctor: проверка Python, профиля, провайдеров LLM, gateway, Telegram, MCP и платформы. "
                "Режим --fix для безопасных исправлений и LLM-ремонта config.yaml."
            ),
            "keywords": "holix doctor, диагностика Holix, holix doctor --fix, проверка конфигурации",
        },
        "en": {
            "title": "Holix Doctor — Diagnostics & Config Auto-Repair",
            "description": (
                "holix doctor: check Python, profile, LLM providers, gateway, Telegram, MCP, and platform. "
                "--fix mode for safe repairs and LLM-assisted config.yaml remediation."
            ),
            "keywords": "holix doctor, Holix diagnostics, holix doctor --fix, config repair",
        },
    },
    "logs": {
        "ru": {
            "title": "Логи Holix — holix logs, ротация и debug-режим",
            "description": (
                "Логирование Holix: holix logs, agent.jsonl, gateway.log, фильтры по уровню и источнику, "
                "follow-режим, ротация файлов и holix logs debug on/off."
            ),
            "keywords": "Holix логи, holix logs, debug mode, ротация логов, gateway log",
        },
        "en": {
            "title": "Holix Logs — holix logs, Rotation & Debug Mode",
            "description": (
                "Holix logging: holix logs, agent.jsonl, gateway.log, level and source filters, "
                "follow mode, file rotation, and holix logs debug on/off."
            ),
            "keywords": "Holix logs, holix logs, debug mode, log rotation, gateway log",
        },
    },
    "pypi": {
        "ru": {
            "title": "PyPI HelixAgentAi — публикация и версионирование пакета",
            "description": (
                "Пакет HelixAgentAi на PyPI: pipx install, Trusted Publishing через GitHub Actions, "
                "версионирование, extras и чеклист релиза open-source дистрибутива Holix."
            ),
            "keywords": "HolixAgentAi PyPI, pip install Holix, публикация PyPI, Holix версия, open source",
        },
        "en": {
            "title": "HolixAgentAi on PyPI — Package Publishing & Versioning",
            "description": (
                "HolixAgentAi PyPI package: pipx install, Trusted Publishing via GitHub Actions, "
                "versioning, extras, and open-source Holix release checklist."
            ),
            "keywords": "HolixAgentAi PyPI, pip install Holix, PyPI publish, Holix version, open source",
        },
    },
    "troubleshooting": {
        "ru": {
            "title": "Решение проблем Holix — типичные ошибки и исправления",
            "description": (
                "Troubleshooting Holix: модели не отвечают, gateway недоступен, Telegram молчит, "
                "ошибки MCP и профилей. Пошаговые решения и ссылки на doctor и логи."
            ),
            "keywords": "Holix troubleshooting, ошибки Holix, gateway не работает, Telegram не отвечает",
        },
        "en": {
            "title": "Holix Troubleshooting — Common Errors & Fixes",
            "description": (
                "Troubleshoot Holix: models not responding, gateway unreachable, silent Telegram, "
                "MCP and profile errors. Step-by-step fixes with doctor and logs."
            ),
            "keywords": "Holix troubleshooting, Holix errors, gateway not working, Telegram silent",
        },
    },
    "user-guide": {
        "ru": {
            "title": "Руководство пользователя Holix — полный гайд от установки до production",
            "description": (
                "Полное руководство по Holix: установка, модели, TUI, Telegram, gateway, навыки, "
                "безопасность и production. Пошаговый гайд для новых пользователей и администраторов."
            ),
            "keywords": "руководство Holix, user guide, Holix tutorial, настройка агента, production гайд",
        },
        "en": {
            "title": "Holix User Guide — Full Tutorial from Install to Production",
            "description": (
                "Complete Holix user guide: install, models, TUI, Telegram, gateway, skills, "
                "security, and production. Step-by-step tutorial for users and admins."
            ),
            "keywords": "Holix user guide, Holix tutorial, agent setup, production guide",
        },
    },
}


def seo_entry_for_slug(slug: str, lang: str, *, fallback_title: str, fallback_heading: str) -> dict[str, str]:
    """Return curated SEO fields with safe fallbacks."""
    curated = SEO_PAGES.get(slug, {}).get(lang) or SEO_PAGES.get(slug, {}).get("en")
    if curated:
        return dict(curated)
    return {
        "title": f"{fallback_heading} — Holix",
        "description": fallback_title,
        "keywords": "Holix, документация" if lang == "ru" else "Holix, documentation",
    }