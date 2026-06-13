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
            "keywords": "Holix обзор, AI агент возможности, документация Holix, Holix, PyPI",
        },
        "en": {
            "title": "Holix Overview — AI Agent Features & Documentation Map",
            "description": (
                "Overview of Holix: self-improving AI agent with memory, skills, MCP, CLI, TUI, gateway, and Telegram. "
                "Documentation map for quickstart and advanced setup."
            ),
            "keywords": "Holix overview, AI agent features, Holix documentation, Holix, PyPI",
        },
    },
    "installation": {
        "ru": {
            "title": "Установка Holix — curl, PyPI, bootstrap, Python 3.12",
            "description": (
                "Установка Holix одной командой curl: определение языка (RU/EN), полная или минимальная "
                "установка, holix bootstrap (LLM, Telegram, локаль профилей). PyPI, pipx, Docker, "
                "обновление и решение проблем."
            ),
            "keywords": "установка Holix, curl install Holix, holix bootstrap, pipx install Holix, PyPI",
        },
        "en": {
            "title": "Install Holix — curl, PyPI, bootstrap, Python 3.12",
            "description": (
                "Install Holix with one curl command: OS language detection (RU/EN), full or minimal "
                "install, holix bootstrap (LLM, Telegram, profile locale). PyPI, pipx, Docker, "
                "updates, and troubleshooting."
            ),
            "keywords": "install Holix, curl install Holix, holix bootstrap, pipx install Holix, PyPI",
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
                "Минимальный быстрый старт Holix: curl install.sh, holix bootstrap, holix doctor, "
                "holix tui. Краткий список команд для немедленного начала работы с агентом."
            ),
            "keywords": "Holix быстрый старт, holix tui, holix models setup, минимальные команды",
        },
        "en": {
            "title": "Holix Quickstart — Minimal Commands to Run the Agent",
            "description": (
                "Minimal Holix quickstart: curl install.sh, holix bootstrap, holix doctor, "
                "holix tui. Short command list to start using the agent immediately."
            ),
            "keywords": "Holix quickstart, holix tui, holix models setup, minimal commands",
        },
    },
    "configuration": {
        "ru": {
            "title": "Конфигурация Holix — профили, шифрование, .env, MCP",
            "description": (
                "Конфигурация Holix: слои env, profiles/<name>/.env, шифрование секретов, "
                "HOLIX_UNLOCK_KEY, config.yaml, Ollama/LiteLLM, MCP и telegram.env."
            ),
            "keywords": (
                "конфигурация Holix, holix profile env, шифрование профиля, HOLIX_UNLOCK_KEY, "
                "Ollama LiteLLM, MCP серверы"
            ),
        },
        "en": {
            "title": "Holix Configuration — Profiles, Encryption, .env & MCP",
            "description": (
                "Holix configuration: env layers, profiles/<name>/.env, optional secret encryption, "
                "HOLIX_UNLOCK_KEY, config.yaml, Ollama/LiteLLM, MCP, and telegram.env."
            ),
            "keywords": (
                "Holix configuration, holix profile env, profile encryption, HOLIX_UNLOCK_KEY, "
                "Ollama LiteLLM, MCP servers"
            ),
        },
    },
    "profiles": {
        "ru": {
            "title": "Профили Holix — изоляция, удаление, workspace jail",
            "description": (
                "Изоляция профилей Holix: .env, gateway, Telegram и память на пользователя. "
                "Удаление с уведомлением в Telegram, workspace jail, ключи hp_, шифрование секретов."
            ),
            "keywords": (
                "Holix профили, изоляция профилей, удаление профиля, workspace jail, "
                "ключ доступа профиля, шифрование Holix"
            ),
        },
        "en": {
            "title": "Holix Profiles — Isolation, Delete & Workspace Jail",
            "description": (
                "Holix profile isolation: per-user .env, gateway, Telegram, and memory. "
                "Delete with Telegram notify, workspace jail, hp_ keys, optional secret encryption."
            ),
            "keywords": (
                "Holix profiles, profile isolation, delete profile, workspace jail, "
                "profile access key, Holix encryption"
            ),
        },
    },
    "profile-encryption": {
        "ru": {
            "title": "Шифрование профиля Holix — Linux, macOS, Windows, HOLIX_UNLOCK_KEY",
            "description": (
                "Шифрование at-rest в Holix: .env, telegram.env, память SQLite/Chroma. "
                "Workspace plaintext. Политика linux-production/on/off по ОС, gateway unlock, миграция."
            ),
            "keywords": (
                "шифрование Holix, HOLIX_UNLOCK_KEY, HOLIX_ENCRYPTION_MODE, linux-production, "
                "holix profile crypto, шифрование профиля, AES-256-GCM, at-rest encryption"
            ),
        },
        "en": {
            "title": "Holix Profile Encryption — Linux, macOS, Windows & Unlock Key",
            "description": (
                "Holix at-rest encryption: .env, telegram.env, SQLite/Chroma memory. "
                "Workspace stays plaintext. OS policy linux-production/on/off, gateway unlock, migration."
            ),
            "keywords": (
                "Holix encryption, HOLIX_UNLOCK_KEY, HOLIX_ENCRYPTION_MODE, linux-production, "
                "holix profile crypto, profile encryption, AES-256-GCM, at-rest encryption"
            ),
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
                "Holix Gateway API, справочник API, Hermes API, Holix Management API, /api/holix, "
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
                "Holix Gateway API, complete API reference, Hermes API, Holix Management API, /api/holix, "
                "OpenAPI Swagger, Telegram admin API, REST API documentation"
            ),
        },
    },
    "telegram": {
        "ru": {
            "title": "Telegram-бот Holix — setup, зашифрованный token, голос",
            "description": (
                "Telegram Holix: holix telegram setup, telegram.env и шифрование, aiogram для gateway, "
                "голос Whisper, уведомление при удалении профиля, канал @holix_agent."
            ),
            "keywords": (
                "Holix Telegram, holix telegram setup, зашифрованный telegram.env, aiogram, "
                "Telegram бот AI, голосовые Whisper"
            ),
        },
        "en": {
            "title": "Holix Telegram — Setup, Encrypted Token & Voice Notes",
            "description": (
                "Holix Telegram: holix telegram setup, encrypted telegram.env, aiogram for gateway, "
                "Whisper voice, profile deletion notify, and @holix_agent channel."
            ),
            "keywords": (
                "Holix Telegram, holix telegram setup, encrypted telegram.env, aiogram, "
                "Telegram AI bot, voice Whisper"
            ),
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
    "max": {
        "ru": {
            "title": "MAX-бот Holix — setup, webhook, мультипользовательский доступ",
            "description": (
                "Интеграция Holix с мессенджером MAX: holix max setup, max.env и шифрование, "
                "webhook через gateway, access requests, inline-подтверждения и файлы."
            ),
            "keywords": (
                "Holix MAX, holix max setup, MAX мессенджер бот, max.env, webhook MAX, "
                "российский мессенджер AI, business.max.ru"
            ),
        },
        "en": {
            "title": "Holix MAX — Setup, Webhook & Multi-User Access",
            "description": (
                "Holix MAX messenger integration: holix max setup, encrypted max.env, "
                "gateway webhook, access requests, inline approvals, and file attachments."
            ),
            "keywords": (
                "Holix MAX, holix max setup, MAX messenger bot, max.env, MAX webhook, "
                "Russian messenger AI, business.max.ru"
            ),
        },
    },
    "max-multi-profile": {
        "ru": {
            "title": "MAX Holix — один бот, несколько изолированных профилей",
            "description": (
                "Как настроить Holix в MAX для нескольких пользователей: отдельный бот на профиль "
                "или один бот с holix max map — привязка user id, workspace jail и Management API."
            ),
            "keywords": "Holix MAX профили, holix max map, изоляция профилей MAX, общий бот MAX",
        },
        "en": {
            "title": "Holix MAX — One Bot, Multiple Isolated Profiles",
            "description": (
                "Run Holix on MAX for multiple users: one bot per profile or a shared bot with "
                "holix max map bindings, workspace jail, and Management API."
            ),
            "keywords": "Holix MAX profiles, holix max map, MAX profile isolation, shared MAX bot",
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
            "title": "Безопасность Holix — шифрование, auth, production checklist",
            "description": (
                "Безопасность Holix: шифрование секретов at-rest, API-ключи HMAC, gateway auth, "
                "whitelist терминала, workspace jail и чеклист production-деплоя."
            ),
            "keywords": (
                "Holix безопасность, шифрование профиля, API key, gateway auth, "
                "terminal whitelist, production security"
            ),
        },
        "en": {
            "title": "Holix Security — Encryption, Auth & Production Checklist",
            "description": (
                "Holix security: at-rest secret encryption, HMAC API keys, gateway auth, terminal whitelist, "
                "workspace jail, and production deployment checklist."
            ),
            "keywords": (
                "Holix security, profile encryption, API key, gateway auth, "
                "terminal whitelist, production security"
            ),
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
            "title": "Деплой Holix — Docker, systemd, шифрование, Linux production",
            "description": (
                "Деплой Holix: Docker, systemd holix-gateway@, HOLIX_UNLOCK_KEY, шифрование на Linux, "
                "uv tool install + aiogram, multi-profile и docs-сайт."
            ),
            "keywords": (
                "деплой Holix, systemd holix-gateway, HOLIX_UNLOCK_KEY, шифрование Linux, "
                "Docker Holix, production deployment"
            ),
        },
        "en": {
            "title": "Deploy Holix — Docker, systemd, Encryption & Linux Production",
            "description": (
                "Deploy Holix: Docker, systemd holix-gateway@, HOLIX_UNLOCK_KEY, Linux encryption, "
                "uv tool install with aiogram, multi-profile, and docs site."
            ),
            "keywords": (
                "deploy Holix, systemd holix-gateway, HOLIX_UNLOCK_KEY, Linux encryption, "
                "Docker Holix, production deployment"
            ),
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
            "title": "PyPI Holix — публикация и версионирование пакета",
            "description": (
                "Пакет Holix на PyPI: pipx install, Trusted Publishing через GitHub Actions, "
                "версионирование, extras и чеклист релиза open-source дистрибутива Holix."
            ),
            "keywords": "Holix PyPI, pip install Holix, публикация PyPI, Holix версия, open source",
        },
        "en": {
            "title": "Holix on PyPI — Package Publishing & Versioning",
            "description": (
                "Holix PyPI package: pipx install, Trusted Publishing via GitHub Actions, "
                "versioning, extras, and open-source Holix release checklist."
            ),
            "keywords": "Holix PyPI, pip install Holix, PyPI publish, Holix version, open source",
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