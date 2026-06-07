#!/usr/bin/env python3
"""Build web-docs content and search index from docs/en and docs/ru."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DOCS_EN = REPO / "docs" / "en"
DOCS_RU = REPO / "docs" / "ru"
CONTENT = ROOT / "content"
SEARCH_INDEX = ROOT / "search-index.json"

# Navigation order and labels
NAV = [
    ("README", {"en": "Overview", "ru": "Обзор"}),
    ("INSTALLATION", {"en": "Installation", "ru": "Установка"}),
    ("START_HERE", {"en": "Start Here", "ru": "Первый запуск"}),
    ("QUICKSTART", {"en": "Quickstart", "ru": "Быстрый старт"}),
    ("CONFIGURATION", {"en": "Configuration", "ru": "Конфигурация"}),
    ("CLI", {"en": "CLI Reference", "ru": "Справочник CLI"}),
    ("SLASH_COMMANDS", {"en": "Slash Commands", "ru": "Слэш-команды"}),
    ("TUI", {"en": "TUI", "ru": "TUI"}),
    ("HUB", {"en": "Hub & Skills", "ru": "Hub и навыки"}),
    ("GATEWAY", {"en": "API Gateway", "ru": "API Gateway"}),
    ("TELEGRAM", {"en": "Telegram", "ru": "Telegram"}),
    ("BROWSER_TOOLS", {"en": "Browser Tools", "ru": "Браузер"}),
    ("ARCHITECTURE", {"en": "Architecture", "ru": "Архитектура"}),
    ("SECURITY", {"en": "Security", "ru": "Безопасность"}),
    ("DEPLOYMENT", {"en": "Deployment", "ru": "Деплой"}),
    ("DOCTOR", {"en": "Doctor", "ru": "Doctor"}),
    ("LOGS", {"en": "Logs", "ru": "Логи"}),
    ("PYPI", {"en": "PyPI", "ru": "PyPI"}),
    ("TROUBLESHOOTING", {"en": "Troubleshooting", "ru": "Решение проблем"}),
    ("USER_GUIDE", {"en": "User Guide", "ru": "Руководство"}),
]


def slugify(name: str) -> str:
    return name.lower().replace("_", "-")


def strip_markdown(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#*_>|]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def copy_docs() -> list[dict]:
    entries: list[dict] = []
    for lang, src in (("en", DOCS_EN), ("ru", DOCS_RU)):
        dest = CONTENT / lang
        dest.mkdir(parents=True, exist_ok=True)
        for old in dest.glob("*.md"):
            old.unlink()
        if not src.exists():
            continue
        for md in sorted(src.glob("*.md")):
            target = dest / md.name
            shutil.copy2(md, target)
            stem = md.stem
            title = next(
                (labels[lang] for key, labels in NAV if key == stem),
                stem.replace("_", " ").title(),
            )
            raw = md.read_text(encoding="utf-8")
            entries.append({
                "id": f"{lang}/{slugify(stem)}",
                "lang": lang,
                "slug": slugify(stem),
                "file": f"content/{lang}/{md.name}",
                "title": title,
                "heading": re.search(r"^#\s+(.+)$", raw, re.M)
                and re.search(r"^#\s+(.+)$", raw, re.M).group(1).strip()
                or title,
                "body": strip_markdown(raw)[:8000],
                "nav_order": next((i for i, (k, _) in enumerate(NAV) if k == stem), 999),
            })
    return entries


def main() -> None:
    entries = copy_docs()
    entries.sort(key=lambda e: (e["lang"], e["nav_order"], e["title"]))
    SEARCH_INDEX.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    nav_meta = [
        {"slug": slugify(key), "en": labels["en"], "ru": labels["ru"], "file_key": key}
        for key, labels in NAV
    ]
    (ROOT / "nav.json").write_text(
        json.dumps(nav_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Built {len(entries)} search entries → {SEARCH_INDEX.name}")


if __name__ == "__main__":
    main()