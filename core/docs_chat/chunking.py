"""Split documentation pages into retrieval-sized chunks."""

from __future__ import annotations

import re
from typing import Any

from core.docs_chat.keywords import slug_keyword_terms

_MAX_CHUNK_CHARS = 1100
_MIN_CHUNK_CHARS = 80
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


def _section_slug(heading: str) -> str:
    slug = re.sub(r"[^\w\u0400-\u04FF\s-]", "", heading.lower()).strip()
    slug = re.sub(r"\s+", "-", slug)
    return slug[:64] or "section"


def strip_markdown(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#*_>|]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_long_text(text: str, *, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    parts: list[str] = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
        if len(sentence) <= max_chars:
            current = sentence
        else:
            for i in range(0, len(sentence), max_chars):
                parts.append(sentence[i : i + max_chars].strip())
            current = ""
    if current:
        parts.append(current)
    return parts


def _chunk_keywords(*, slug: str, section: str, heading: str) -> list[str]:
    words = re.findall(r"[\w\u0400-\u04FF]{3,}", f"{section} {heading}".lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for term in slug_keyword_terms(slug) + words:
        if term in seen:
            continue
        seen.add(term)
        keywords.append(term)
    return keywords[:24]


def chunk_page(
    raw: str,
    *,
    lang: str,
    slug: str,
    title: str,
    nav_order: int,
) -> list[dict[str, Any]]:
    """Split one markdown page into section-based chunks."""
    sections: list[tuple[str, str, list[str]]] = []
    current_heading = title
    current_level = 1
    current_lines: list[str] = []

    def flush() -> None:
        body = strip_markdown("\n".join(current_lines))
        if len(body) >= _MIN_CHUNK_CHARS:
            sections.append((current_heading, _section_slug(current_heading), [body]))

    for line in raw.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            if level <= 3:
                current_heading = match.group(2).strip()
                current_level = level
                current_lines = []
                continue
        current_lines.append(line)

    flush()

    if not sections:
        body = strip_markdown(raw)
        if body:
            sections.append((title, "overview", [body]))

    chunks: list[dict[str, Any]] = []
    for section_heading, section_slug, bodies in sections:
        for part_idx, body in enumerate(_split_long_text(bodies[0], max_chars=_MAX_CHUNK_CHARS)):
            part_suffix = f"-{part_idx + 1}" if part_idx else ""
            chunk_id = f"{lang}/{slug}#{section_slug}{part_suffix}"
            chunks.append(
                {
                    "id": chunk_id,
                    "lang": lang,
                    "slug": slug,
                    "section": section_slug,
                    "title": title,
                    "heading": section_heading,
                    "body": body,
                    "keywords": _chunk_keywords(
                        slug=slug,
                        section=section_slug,
                        heading=section_heading,
                    ),
                    "nav_order": nav_order,
                }
            )
    return chunks