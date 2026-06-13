"""Query expansion and per-slug keywords for docs retrieval."""

from __future__ import annotations

import re

QUERY_ALIASES: dict[str, str] = {
    "телеграм": "telegram",
    "телеграмм": "telegram",
    "телеграмме": "telegram",
    "телеграма": "telegram",
    "профил": "profiles",
    "профили": "profiles",
    "профиля": "profiles",
    "профилей": "profiles",
    "установк": "installation",
    "установка": "installation",
    "установить": "installation",
    "гейтвей": "gateway",
    "шлюз": "gateway",
    "браузер": "browser-tools",
    "деплой": "deployment",
    "развертывание": "deployment",
    "развёртывание": "deployment",
    "безопасность": "security",
    "логи": "logs",
    "журнал": "logs",
    "навыки": "hub",
    "skill": "hub",
    "skills": "hub",
    "mcp": "hub",
    "whisper": "telegram",
    "голосовые": "telegram",
    "бот": "telegram",
    "bot": "telegram",
}

SEARCH_STOPWORDS = frozenset(
    {
        "как",
        "что",
        "где",
        "для",
        "при",
        "это",
        "или",
        "the",
        "and",
        "for",
        "how",
        "what",
        "where",
        "настроить",
        "настройка",
        "настройки",
        "configure",
        "configuration",
        "setup",
        "setting",
        "settings",
    }
)

SLUG_KEYWORDS: dict[str, list[str]] = {
    "readme": ["overview", "обзор", "holix", "документация"],
    "installation": ["install", "установка", "pipx", "pypi", "uv", "docker"],
    "start-here": ["start", "первый", "запуск", "checklist"],
    "quickstart": ["quick", "быстрый", "старт"],
    "configuration": ["config", "конфигурация", "env", "переменные"],
    "profiles": [
        "profile",
        "профиль",
        "профили",
        "изоляция",
        "jail",
        "workspace",
        "path",
        "paths",
        "путь",
        "пути",
        "relative",
        "относительный",
        "restricted",
    ],
    "cli": ["command", "команды", "typer", "terminal"],
    "slash-commands": ["slash", "слэш", "команды", "session"],
    "tui": ["textual", "интерфейс", "terminal", "web mode"],
    "hub": ["skills", "навыки", "catalog", "каталог", "mcp"],
    "gateway": ["api", "gateway", "гейтвей", "uvicorn", "openai", "path", "путь", "restricted"],
    "gateway-api": ["api", "gateway", "chat", "completions", "sessions", "path", "admin"],
    "troubleshooting": ["troubleshoot", "проблемы", "ошибки", "restricted", "путь", "path", "jail", "fix"],
    "telegram": ["telegram", "телеграм", "бот", "bot", "allowlist", "whisper", "голосовые"],
    "browser-tools": ["browser", "playwright", "браузер"],
    "architecture": ["architecture", "архитектура", "runtime", "events"],
    "security": ["security", "безопасность", "auth", "cors", "token"],
    "deployment": ["deploy", "деплой", "systemd", "docker", "ci"],
    "doctor": ["doctor", "диагностика", "fix", "repair"],
    "logs": ["logs", "логи", "debug", "rotation"],
    "pypi": ["pypi", "publish", "публикация", "package"],
    "user-guide": ["guide", "руководство", "usage"],
}


def tokenize(query: str) -> list[str]:
    return [w for w in re.split(r"\s+", query.lower().strip()) if len(w) >= 2]


def expand_query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for word in tokenize(query):
        if word in seen:
            continue
        seen.add(word)
        terms.append(word)
        alias = QUERY_ALIASES.get(word)
        if alias and alias not in seen:
            seen.add(alias)
            terms.append(alias)
        for ru, en in QUERY_ALIASES.items():
            if word.startswith(ru) and en not in seen:
                seen.add(en)
                terms.append(en)
    return terms


def content_terms(terms: list[str]) -> list[str]:
    return [t for t in terms if t not in SEARCH_STOPWORDS]


def slug_keyword_terms(slug: str) -> list[str]:
    return SLUG_KEYWORDS.get(slug, [])