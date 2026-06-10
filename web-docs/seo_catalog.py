"""Curated SEO titles, descriptions, and keywords for helix-agent.ru pages."""

from __future__ import annotations

# slug → {lang: {title, description, keywords}}
# Titles: 50–60 chars where possible. Descriptions: 140–160 chars for SERP snippets.

SEO_VIEWS: dict[str, dict[str, dict[str, str]]] = {
    "home": {
        "ru": {
            "title": "Helix — AI-агент с памятью, MCP и Telegram · Российская разработка",
            "description": (
                "Helix — российский самообучающийся AI-агент: долговременная память, навыки, "
                "MCP, CLI, TUI, API gateway и Telegram. Open source, деплой на своей инфраструктуре с Ollama и LiteLLM."
            ),
            "keywords": (
                "Helix AI агент, самообучающийся агент, российское ПО, LLM агент, Ollama, LiteLLM, "
                "MCP, Telegram бот, API gateway, open source AI"
            ),
        },
        "en": {
            "title": "Helix — Self-Improving AI Agent with Memory, MCP & Telegram",
            "description": (
                "Helix is an open-source self-improving AI agent: persistent memory, skills, MCP, CLI, TUI, "
                "API gateway, and Telegram. Deploy on-prem with Ollama, LiteLLM, or cloud LLMs."
            ),
            "keywords": (
                "Helix AI agent, self-improving agent, LLM agent, Ollama, LiteLLM, MCP, "
                "Telegram bot, API gateway, open source AI, Russian software"
            ),
        },
    },
    "docs-hub": {
        "ru": {
            "title": "Документация Helix — установка, CLI, профили, gateway, Telegram",
            "description": (
                "Полная документация Helix: установка с PyPI, первый запуск, конфигурация профилей, "
                "справочник CLI, TUI, API gateway, Telegram-бот, деплой в Docker и systemd."
            ),
            "keywords": (
                "документация Helix, Helix установка, Helix CLI, профили Helix, gateway API, "
                "Telegram бот Helix, руководство пользователя"
            ),
        },
        "en": {
            "title": "Helix Documentation — Install, CLI, Profiles, Gateway, Telegram",
            "description": (
                "Complete Helix docs: PyPI install, quickstart, profile configuration, CLI reference, "
                "TUI, API gateway, Telegram bot, Docker and systemd deployment guides."
            ),
            "keywords": (
                "Helix documentation, Helix install guide, Helix CLI, Helix profiles, "
                "API gateway, Telegram bot, user guide"
            ),
        },
    },
}

SEO_PAGES: dict[str, dict[str, dict[str, str]]] = {
    "readme": {
        "ru": {
            "title": "Обзор Helix — возможности AI-агента и структура документации",
            "description": (
                "Обзор Helix: самообучающийся AI-агент с памятью, навыками, MCP, CLI, TUI, gateway и Telegram. "
                "Карта документации для быстрого старта и углублённой настройки."
            ),
            "keywords": "Helix обзор, AI агент возможности, документация Helix, HelixAgentAi, PyPI",
        },
        "en": {
            "title": "Helix Overview — AI Agent Features & Documentation Map",
            "description": (
                "Overview of Helix: self-improving AI agent with memory, skills, MCP, CLI, TUI, gateway, and Telegram. "
                "Documentation map for quickstart and advanced setup."
            ),
            "keywords": "Helix overview, AI agent features, Helix documentation, HelixAgentAi, PyPI",
        },
    },
    "installation": {
        "ru": {
            "title": "Установка Helix — PyPI, pipx, Python 3.12, Docker",
            "description": (
                "Как установить Helix с PyPI (HelixAgentAi): pipx, venv, Python 3.12+, опциональные extras "
                "(Telegram, браузер, голос). Обновление, удаление и решение проблем установки."
            ),
            "keywords": "установка Helix, pipx install HelixAgentAi, PyPI, Python 3.12, Helix Docker",
        },
        "en": {
            "title": "Install Helix — PyPI, pipx, Python 3.12, Docker",
            "description": (
                "How to install Helix from PyPI (HelixAgentAi): pipx, venv, Python 3.12+, optional extras "
                "(Telegram, browser, voice). Updates, uninstall, and install troubleshooting."
            ),
            "keywords": "install Helix, pipx install HelixAgentAi, PyPI, Python 3.12, Helix Docker",
        },
    },
    "start-here": {
        "ru": {
            "title": "Первый запуск Helix — чеклист настройки за 5 шагов",
            "description": (
                "Чеклист первого запуска Helix: установка, helix doctor, настройка моделей, выбор интерфейса "
                "(TUI, chat, gateway) и опциональные функции Telegram и браузера."
            ),
            "keywords": "первый запуск Helix, helix doctor, настройка моделей, helix tui, быстрый старт",
        },
        "en": {
            "title": "Start Here — Helix First-Run Checklist in 5 Steps",
            "description": (
                "Helix first-run checklist: install, helix doctor, configure models, pick an interface "
                "(TUI, chat, gateway), and optional Telegram and browser features."
            ),
            "keywords": "Helix start here, helix doctor, configure models, helix tui, first run",
        },
    },
    "quickstart": {
        "ru": {
            "title": "Быстрый старт Helix — минимальные команды для запуска",
            "description": (
                "Минимальный быстрый старт Helix: pipx install HelixAgentAi, helix doctor, helix models setup, "
                "helix tui. Краткий список команд для немедленного начала работы с агентом."
            ),
            "keywords": "Helix быстрый старт, helix tui, helix models setup, минимальные команды",
        },
        "en": {
            "title": "Helix Quickstart — Minimal Commands to Run the Agent",
            "description": (
                "Minimal Helix quickstart: pipx install HelixAgentAi, helix doctor, helix models setup, "
                "helix tui. Short command list to start using the agent immediately."
            ),
            "keywords": "Helix quickstart, helix tui, helix models setup, minimal commands",
        },
    },
    "configuration": {
        "ru": {
            "title": "Конфигурация Helix — профили, .env, модели и MCP",
            "description": (
                "Конфигурация Helix: слои настроек, profiles/<name>/.env, config.yaml, провайдеры LLM "
                "(Ollama, LiteLLM, OpenRouter), MCP-серверы, Hub и секреты ${ENV:VAR}."
            ),
            "keywords": "конфигурация Helix, helix profile env, Ollama LiteLLM, MCP серверы, config.yaml",
        },
        "en": {
            "title": "Helix Configuration — Profiles, .env, Models & MCP",
            "description": (
                "Helix configuration: settings layers, profiles/<name>/.env, config.yaml, LLM providers "
                "(Ollama, LiteLLM, OpenRouter), MCP servers, Hub, and ${ENV:VAR} secrets."
            ),
            "keywords": "Helix configuration, helix profile env, Ollama LiteLLM, MCP servers, config.yaml",
        },
    },
    "profiles": {
        "ru": {
            "title": "Профили Helix — изоляция пользователей, ключи доступа, workspace jail",
            "description": (
                "Изоляция профилей Helix: отдельные .env, gateway, Telegram-бот и память на пользователя. "
                "Опциональные ключи доступа и workspace jail для ограничения файловых операций."
            ),
            "keywords": "Helix профили, изоляция профилей, workspace jail, ключ доступа профиля, multi-user",
        },
        "en": {
            "title": "Helix Profiles — User Isolation, Access Keys & Workspace Jail",
            "description": (
                "Helix profile isolation: separate .env, gateway, Telegram bot, and memory per user. "
                "Optional access keys and workspace jail to restrict file and terminal tools."
            ),
            "keywords": "Helix profiles, profile isolation, workspace jail, profile access key, multi-user",
        },
    },
    "cli": {
        "ru": {
            "title": "Справочник CLI Helix — все команды helix",
            "description": (
                "Полный справочник CLI Helix: chat, tui, gateway, models, telegram, profile, mcp, hub, "
                "cron, logs, doctor. Опции -p profile, примеры и типовые сценарии использования."
            ),
            "keywords": "Helix CLI, helix команды, helix gateway, helix models, helix telegram, справочник",
        },
        "en": {
            "title": "Helix CLI Reference — All helix Commands",
            "description": (
                "Complete Helix CLI reference: chat, tui, gateway, models, telegram, profile, mcp, hub, "
                "cron, logs, doctor. -p profile option, examples, and common workflows."
            ),
            "keywords": "Helix CLI, helix commands, helix gateway, helix models, helix telegram, reference",
        },
    },
    "slash-commands": {
        "ru": {
            "title": "Слэш-команды Helix — /models, /skills, /mcp в TUI и Telegram",
            "description": (
                "Слэш-команды Helix в TUI и Telegram: /models, /profile, /skills, /mcp, /hub, /compress, "
                "/sessions. Управление сессией, моделями и инструментами без обращения к LLM."
            ),
            "keywords": "Helix слэш-команды, /models, /skills, TUI команды, Telegram команды Helix",
        },
        "en": {
            "title": "Helix Slash Commands — /models, /skills, /mcp in TUI & Telegram",
            "description": (
                "Helix slash commands in TUI and Telegram: /models, /profile, /skills, /mcp, /hub, /compress, "
                "/sessions. Control session, models, and tools without prompting the LLM."
            ),
            "keywords": "Helix slash commands, /models, /skills, TUI commands, Telegram commands",
        },
    },
    "tui": {
        "ru": {
            "title": "TUI Helix — терминальный интерфейс агента и веб-режим",
            "description": (
                "Helix TUI: полноэкранный терминальный интерфейс с инструментами, Hub, MCP, копированием "
                "и веб-режимом (helix tui --web). Ежедневная работа с агентом в консоли."
            ),
            "keywords": "Helix TUI, helix tui --web, терминальный AI агент, textual UI, консольный агент",
        },
        "en": {
            "title": "Helix TUI — Terminal UI, Tools, Hub & Web Mode",
            "description": (
                "Helix TUI: full-screen terminal interface with tools, Hub, MCP, copy support, "
                "and web mode (helix tui --web). Daily agent workflow in the console."
            ),
            "keywords": "Helix TUI, helix tui --web, terminal AI agent, textual UI, console agent",
        },
    },
    "hub": {
        "ru": {
            "title": "Hub и навыки Helix — каталоги skills, MCP и ClawHub",
            "description": (
                "Helix Hub: установка навыков и MCP из ClawHub, HermesHub, Claude plugins. "
                "helix hub search/install, skill assignments и автообновление каталогов."
            ),
            "keywords": "Helix Hub, helix skills, ClawHub, MCP install, навыки агента, helix hub install",
        },
        "en": {
            "title": "Helix Hub & Skills — Skill Catalogs, MCP & ClawHub",
            "description": (
                "Helix Hub: install skills and MCP from ClawHub, HermesHub, Claude plugins. "
                "helix hub search/install, skill assignments, and catalog auto-updates."
            ),
            "keywords": "Helix Hub, helix skills, ClawHub, MCP install, agent skills, helix hub install",
        },
    },
    "gateway": {
        "ru": {
            "title": "API Gateway Helix — OpenAI-совместимый HTTP API",
            "description": (
                "Helix API Gateway: OpenAI-совместимый REST API, helix gateway start/stop, аутентификация, "
                "Prometheus metrics, cron и Telegram как companion-процессы. Настройка портов и профилей."
            ),
            "keywords": "Helix gateway, API gateway, OpenAI compatible API, helix gateway start, Prometheus",
        },
        "en": {
            "title": "Helix API Gateway — OpenAI-Compatible HTTP API",
            "description": (
                "Helix API Gateway: OpenAI-compatible REST API, helix gateway start/stop, authentication, "
                "Prometheus metrics, cron and Telegram companions. Per-profile ports and setup."
            ),
            "keywords": "Helix gateway, API gateway, OpenAI compatible API, helix gateway start, Prometheus",
        },
    },
    "telegram": {
        "ru": {
            "title": "Telegram-бот Helix — настройка, голос, slash-команды",
            "description": (
                "Telegram-интеграция Helix: helix telegram setup, отдельный бот на профиль, allowlist, "
                "голосовые сообщения (Whisper), inline-подтверждения и канал @helix_agent с новостями."
            ),
            "keywords": "Helix Telegram, helix telegram setup, Telegram бот AI, голосовые сообщения Whisper",
        },
        "en": {
            "title": "Helix Telegram Bot — Setup, Voice Notes & Slash Commands",
            "description": (
                "Helix Telegram integration: helix telegram setup, per-profile bot, allowlist, "
                "voice messages (Whisper), inline approvals, and @helix_agent channel for news."
            ),
            "keywords": "Helix Telegram, helix telegram setup, Telegram AI bot, voice Whisper",
        },
    },
    "browser-tools": {
        "ru": {
            "title": "Браузерные инструменты Helix — Playwright автоматизация",
            "description": (
                "Браузерные инструменты Helix на Playwright: открытие страниц, клики, ввод текста, "
                "скриншоты. Безопасность URL, подтверждения и установка extra browser."
            ),
            "keywords": "Helix browser tools, Playwright, автоматизация браузера, helix browser extra",
        },
        "en": {
            "title": "Helix Browser Tools — Playwright Web Automation",
            "description": (
                "Helix browser tools with Playwright: open pages, click, type, screenshots. "
                "URL security policy, confirmations, and browser extra installation."
            ),
            "keywords": "Helix browser tools, Playwright, web automation, helix browser extra",
        },
    },
    "architecture": {
        "ru": {
            "title": "Архитектура Helix — runtime, DI, LangGraph, память",
            "description": (
                "Архитектура Helix: DI-контейнер, LangGraph execution, события, подагенты, SQLite + ChromaDB "
                "память, MCP и модульная структура CLI, gateway и интеграций."
            ),
            "keywords": "архитектура Helix, LangGraph, ChromaDB память, DI container, AI agent architecture",
        },
        "en": {
            "title": "Helix Architecture — Runtime, DI, LangGraph & Memory",
            "description": (
                "Helix architecture: DI container, LangGraph execution, events, subagents, SQLite + ChromaDB "
                "memory, MCP, and modular CLI, gateway, and integration layout."
            ),
            "keywords": "Helix architecture, LangGraph, ChromaDB memory, DI container, AI agent architecture",
        },
    },
    "security": {
        "ru": {
            "title": "Безопасность Helix — auth, whitelist, production checklist",
            "description": (
                "Безопасность Helix: API-ключи HMAC, gateway auth, whitelist терминала, подтверждения "
                "опасных операций, SSRF-защита браузера и чеклист для production-деплоя."
            ),
            "keywords": "Helix безопасность, API key, gateway auth, terminal whitelist, production security",
        },
        "en": {
            "title": "Helix Security — Auth, Whitelist & Production Checklist",
            "description": (
                "Helix security: HMAC API keys, gateway auth, terminal whitelist, risky-action confirmations, "
                "browser SSRF checks, and production deployment checklist."
            ),
            "keywords": "Helix security, API key, gateway auth, terminal whitelist, production security",
        },
    },
    "deployment": {
        "ru": {
            "title": "Деплой Helix — Docker, systemd, multi-profile production",
            "description": (
                "Деплой Helix в production: Docker, systemd helix-gateway@, несколько профилей на одном "
                "сервере, переменные окружения, docs-сайт и CI/CD рекомендации."
            ),
            "keywords": "деплой Helix, systemd helix-gateway, Docker Helix, production deployment, multi-profile",
        },
        "en": {
            "title": "Deploy Helix — Docker, systemd & Multi-Profile Production",
            "description": (
                "Deploy Helix in production: Docker, systemd helix-gateway@, multiple profiles on one "
                "server, environment variables, docs site, and CI/CD recommendations."
            ),
            "keywords": "deploy Helix, systemd helix-gateway, Docker Helix, production deployment",
        },
    },
    "doctor": {
        "ru": {
            "title": "Helix Doctor — диагностика и автоисправление конфигурации",
            "description": (
                "helix doctor: проверка Python, профиля, провайдеров LLM, gateway, Telegram, MCP и платформы. "
                "Режим --fix для безопасных исправлений и LLM-ремонта config.yaml."
            ),
            "keywords": "helix doctor, диагностика Helix, helix doctor --fix, проверка конфигурации",
        },
        "en": {
            "title": "Helix Doctor — Diagnostics & Config Auto-Repair",
            "description": (
                "helix doctor: check Python, profile, LLM providers, gateway, Telegram, MCP, and platform. "
                "--fix mode for safe repairs and LLM-assisted config.yaml remediation."
            ),
            "keywords": "helix doctor, Helix diagnostics, helix doctor --fix, config repair",
        },
    },
    "logs": {
        "ru": {
            "title": "Логи Helix — helix logs, ротация и debug-режим",
            "description": (
                "Логирование Helix: helix logs, agent.jsonl, gateway.log, фильтры по уровню и источнику, "
                "follow-режим, ротация файлов и helix logs debug on/off."
            ),
            "keywords": "Helix логи, helix logs, debug mode, ротация логов, gateway log",
        },
        "en": {
            "title": "Helix Logs — helix logs, Rotation & Debug Mode",
            "description": (
                "Helix logging: helix logs, agent.jsonl, gateway.log, level and source filters, "
                "follow mode, file rotation, and helix logs debug on/off."
            ),
            "keywords": "Helix logs, helix logs, debug mode, log rotation, gateway log",
        },
    },
    "pypi": {
        "ru": {
            "title": "PyPI HelixAgentAi — публикация и версионирование пакета",
            "description": (
                "Пакет HelixAgentAi на PyPI: pipx install, Trusted Publishing через GitHub Actions, "
                "версионирование, extras и чеклист релиза open-source дистрибутива Helix."
            ),
            "keywords": "HelixAgentAi PyPI, pip install Helix, публикация PyPI, Helix версия, open source",
        },
        "en": {
            "title": "HelixAgentAi on PyPI — Package Publishing & Versioning",
            "description": (
                "HelixAgentAi PyPI package: pipx install, Trusted Publishing via GitHub Actions, "
                "versioning, extras, and open-source Helix release checklist."
            ),
            "keywords": "HelixAgentAi PyPI, pip install Helix, PyPI publish, Helix version, open source",
        },
    },
    "troubleshooting": {
        "ru": {
            "title": "Решение проблем Helix — типичные ошибки и исправления",
            "description": (
                "Troubleshooting Helix: модели не отвечают, gateway недоступен, Telegram молчит, "
                "ошибки MCP и профилей. Пошаговые решения и ссылки на doctor и логи."
            ),
            "keywords": "Helix troubleshooting, ошибки Helix, gateway не работает, Telegram не отвечает",
        },
        "en": {
            "title": "Helix Troubleshooting — Common Errors & Fixes",
            "description": (
                "Troubleshoot Helix: models not responding, gateway unreachable, silent Telegram, "
                "MCP and profile errors. Step-by-step fixes with doctor and logs."
            ),
            "keywords": "Helix troubleshooting, Helix errors, gateway not working, Telegram silent",
        },
    },
    "user-guide": {
        "ru": {
            "title": "Руководство пользователя Helix — полный гайд от установки до production",
            "description": (
                "Полное руководство по Helix: установка, модели, TUI, Telegram, gateway, навыки, "
                "безопасность и production. Пошаговый гайд для новых пользователей и администраторов."
            ),
            "keywords": "руководство Helix, user guide, Helix tutorial, настройка агента, production гайд",
        },
        "en": {
            "title": "Helix User Guide — Full Tutorial from Install to Production",
            "description": (
                "Complete Helix user guide: install, models, TUI, Telegram, gateway, skills, "
                "security, and production. Step-by-step tutorial for users and admins."
            ),
            "keywords": "Helix user guide, Helix tutorial, agent setup, production guide",
        },
    },
}


def seo_entry_for_slug(slug: str, lang: str, *, fallback_title: str, fallback_heading: str) -> dict[str, str]:
    """Return curated SEO fields with safe fallbacks."""
    curated = SEO_PAGES.get(slug, {}).get(lang) or SEO_PAGES.get(slug, {}).get("en")
    if curated:
        return dict(curated)
    return {
        "title": f"{fallback_heading} — Helix",
        "description": fallback_title,
        "keywords": "Helix, документация" if lang == "ru" else "Helix, documentation",
    }