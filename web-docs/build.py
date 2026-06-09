#!/usr/bin/env python3
"""Build web-docs content and search index from docs/en and docs/ru."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))

from core.docs_chat.build_index import make_page_entry, write_chunk_index  # noqa: E402

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
    ("PROFILES", {"en": "Profiles & Isolation", "ru": "Профили и изоляция"}),
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
    ("DOCTOR", {"en": "Doctor", "ru": "Доктор"}),
    ("LOGS", {"en": "Logs", "ru": "Логи"}),
    ("PYPI", {"en": "PyPI", "ru": "PyPI"}),
    ("TROUBLESHOOTING", {"en": "Troubleshooting", "ru": "Решение проблем"}),
    ("USER_GUIDE", {"en": "User Guide", "ru": "Руководство"}),
]


def slugify(name: str) -> str:
    return name.lower().replace("_", "-")


def copy_docs() -> tuple[list[dict], dict[str, str]]:
    entries: list[dict] = []
    raw_by_file: dict[str, str] = {}
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
            file_rel = f"content/{lang}/{md.name}"
            raw_by_file[file_rel] = raw
            heading_match = re.search(r"^#\s+(.+)$", raw, re.M)
            entries.append(
                make_page_entry(
                    lang=lang,
                    stem=stem,
                    slug=slugify(stem),
                    title=title,
                    heading=heading_match.group(1).strip() if heading_match else title,
                    file_rel=file_rel,
                    raw=raw,
                    nav_order=next((i for i, (k, _) in enumerate(NAV) if k == stem), 999),
                )
            )
    return entries, raw_by_file


def main() -> None:
    entries, raw_by_file = copy_docs()
    entries.sort(key=lambda e: (e["lang"], e["nav_order"], e["title"]))
    SEARCH_INDEX.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    chunks = write_chunk_index(ROOT, pages=entries, raw_by_file=raw_by_file)

    nav_meta = [
        {"slug": slugify(key), "en": labels["en"], "ru": labels["ru"], "file_key": key}
        for key, labels in NAV
    ]
    (ROOT / "nav.json").write_text(
        json.dumps(nav_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Built {len(entries)} pages, {len(chunks)} chunks → "
        f"{SEARCH_INDEX.name}, search-chunks.json, search-vectors.npz"
    )


if __name__ == "__main__":
    main()