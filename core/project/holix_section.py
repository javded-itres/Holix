"""Section-level updates for `.holix/HOLIX.md` (small tool payloads)."""

from __future__ import annotations

import re
from pathlib import Path

_MAX_SECTION_CONTENT_CHARS = 2500


def upsert_holix_section(
    text: str,
    *,
    heading: str,
    content: str,
) -> tuple[str, str | None]:
    """Replace the body under *heading* until the next ``##`` heading.

    Returns ``(new_text, error)``.
    """
    head = (heading or "").strip()
    body = (content or "").strip()
    if not head:
        return text, "heading is required"
    if len(body) > _MAX_SECTION_CONTENT_CHARS:
        return (
            text,
            f"section content too long ({len(body)} chars; max {_MAX_SECTION_CONTENT_CHARS})",
        )
    if head not in text:
        return text, f"heading not found: {head}"

    pattern = re.compile(
        rf"(^|\n)({re.escape(head)}[^\n]*\n)(.*?)(?=\n## |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return text, f"could not locate section for heading: {head}"

    prefix, heading_line, _old_body = match.groups()
    replacement = f"{prefix}{heading_line}{body}\n"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, None


def write_holix_section(path: Path, *, heading: str, content: str) -> str:
    """Update one section in a HOLIX.md file on disk."""
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading {path}: {exc}"
    updated, err = upsert_holix_section(existing, heading=heading, content=content)
    if err:
        return f"Error: {err}"
    try:
        path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        return f"Error writing {path}: {exc}"
    return f"Updated section {heading} in {path}"