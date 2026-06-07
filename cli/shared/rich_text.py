"""Convert Rich / markup strings to plain text for non-TUI hosts."""

from __future__ import annotations

import re
from typing import Any

_RICH_TAG_RE = re.compile(r"\[/?[^\]]+\]")


def strip_rich_markup(text: str) -> str:
    return _RICH_TAG_RE.sub("", text or "").strip()


def content_to_plain_text(content: Any) -> str:
    """Plain text for Telegram, logs, etc. (never ``repr`` of Rich objects)."""
    if content is None:
        return ""
    if isinstance(content, str):
        if "[" in content and "]" in content:
            return strip_rich_markup(content)
        return content.strip()
    markup_src = getattr(content, "markup", None) or getattr(content, "source", None)
    if markup_src and isinstance(markup_src, str):
        return markup_src.strip()
    try:
        from io import StringIO

        from rich.console import Console

        buf = StringIO()
        Console(file=buf, width=120, legacy_windows=False).print(content)
        return buf.getvalue().strip()
    except Exception:
        return strip_rich_markup(str(content))