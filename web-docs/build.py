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
SITE_URL = "https://holix-agent.ru"
sys.path.insert(0, str(REPO))

from core.docs_chat.build_index import make_page_entry, write_chunk_index  # noqa: E402
from seo_catalog import SEO_PAGES, SEO_VIEWS, seo_entry_for_slug  # noqa: E402

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
    ("PROFILE_ENCRYPTION", {"en": "Profile Encryption", "ru": "Шифрование профиля"}),
    ("CLI", {"en": "CLI Reference", "ru": "Справочник CLI"}),
    ("SLASH_COMMANDS", {"en": "Slash Commands", "ru": "Слэш-команды"}),
    ("EXECUTION_MODES", {"en": "Execution Modes", "ru": "Режимы работы"}),
    ("TUI", {"en": "TUI", "ru": "TUI"}),
    ("HUB", {"en": "Hub & Skills", "ru": "Hub и навыки"}),
    ("GATEWAY", {"en": "API Gateway", "ru": "API Gateway"}),
    ("GATEWAY_API", {"en": "Complete API Reference", "ru": "Полный справочник API"}),
    ("TELEGRAM", {"en": "Telegram", "ru": "Telegram"}),
    ("TELEGRAM_MULTI_PROFILE", {"en": "Telegram Multi-Profile", "ru": "Telegram: несколько профилей"}),
    ("BROWSER_TOOLS", {"en": "Browser Tools", "ru": "Браузер"}),
    ("ARCHITECTURE", {"en": "Architecture", "ru": "Архитектура"}),
    ("SECURITY", {"en": "Security", "ru": "Безопасность"}),
    ("TERMINAL_SECURITY", {"en": "Terminal Security", "ru": "Безопасность команд"}),
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


def write_seo_artifacts(entries: list[dict]) -> None:
    """Generate sitemap.xml, seo-meta.json, and crawlable link list for index.html."""
    pages: dict[str, dict[str, dict[str, str]]] = {}
    for entry in entries:
        slug = entry["slug"]
        lang = entry["lang"]
        seo = seo_entry_for_slug(
            slug,
            lang,
            fallback_title=entry["title"],
            fallback_heading=entry["heading"],
        )
        pages.setdefault(slug, {})[lang] = {
            "navTitle": entry["title"],
            "heading": entry["heading"],
            **seo,
        }

    missing = sorted(set(SEO_PAGES) - set(pages))
    if missing:
        print(f"Warning: SEO catalog slugs without built pages: {', '.join(missing)}")

    seo_meta = {
        "siteUrl": SITE_URL,
        "views": SEO_VIEWS,
        "defaults": {
            "ru": SEO_VIEWS["home"]["ru"],
            "en": SEO_VIEWS["home"]["en"],
        },
        "pages": pages,
    }
    (ROOT / "seo-meta.json").write_text(
        json.dumps(seo_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    slugs = sorted(pages)
    url_lines = [
        "  <url>",
        f"    <loc>{SITE_URL}/</loc>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
        "  <url>",
        f"    <loc>{SITE_URL}/docs</loc>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>0.9</priority>",
        "  </url>",
    ]
    for slug in slugs:
        url_lines.extend(
            [
                "  <url>",
                f"    <loc>{SITE_URL}/docs/{slug}</loc>",
                "    <changefreq>monthly</changefreq>",
                "    <priority>0.8</priority>",
                "  </url>",
            ]
        )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(url_lines)
        + "\n</urlset>\n"
    )
    (ROOT / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    crawl_links = [
        f'<a href="{SITE_URL}/">Holix</a>',
        f'<a href="{SITE_URL}/docs">Documentation</a>',
    ]
    for slug in slugs:
        label = pages[slug].get("ru", pages[slug].get("en", {})).get("title", slug)
        crawl_links.append(f'<a href="{SITE_URL}/docs/{slug}">{label}</a>')
    crawl_html = "\n      ".join(crawl_links)
    index_path = ROOT / "index.html"
    index_html = index_path.read_text(encoding="utf-8")
    marker_start = "<!-- SEO_CRAWL_LINKS -->"
    marker_end = "<!-- /SEO_CRAWL_LINKS -->"
    if marker_start in index_html and marker_end in index_html:
        start = index_html.index(marker_start) + len(marker_start)
        end = index_html.index(marker_end)
        index_path.write_text(
            index_html[:start] + f"\n      {crawl_html}\n      " + index_html[end:],
            encoding="utf-8",
        )


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
    write_seo_artifacts(entries)
    print(
        f"Built {len(entries)} pages, {len(chunks)} chunks -> "
        f"{SEARCH_INDEX.name}, search-chunks.json, search-vectors.npz, sitemap.xml"
    )


if __name__ == "__main__":
    main()