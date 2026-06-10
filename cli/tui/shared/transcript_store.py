"""Plain-text transcript store for reliable copy/export alongside RichLog."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_RICH_TAG_RE = re.compile(r"\[/?[^\]]+\]")


@dataclass
class TranscriptEntry:
    kind: str  # system | user | assistant | tool | error | meta
    plain: str
    markdown: str | None = None
    title: str | None = None  # tool name, etc.


@dataclass
class TranscriptStore:
    """Append-only log used for /copy, /open, and clipboard fallbacks."""

    entries: list[TranscriptEntry] = field(default_factory=list)
    _stream_plain: str = ""

    def clear(self) -> None:
        self.entries.clear()
        self._stream_plain = ""

    def append(
        self,
        kind: str,
        plain: str,
        *,
        markdown: str | None = None,
        title: str | None = None,
    ) -> None:
        text = (plain or "").strip()
        if not text:
            return
        self.entries.append(
            TranscriptEntry(
                kind=kind,
                plain=text,
                markdown=markdown,
                title=title,
            )
        )

    def append_stream_delta(self, text: str) -> None:
        if text:
            self._stream_plain += text

    def clear_stream(self) -> None:
        self._stream_plain = ""

    def has_stream_buffer(self) -> bool:
        return bool(self._stream_plain.strip())

    def flush_stream_to_assistant(self, *, markdown: str | None = None) -> None:
        body = self._stream_plain.strip()
        if not body:
            return
        self.append(
            "assistant",
            body,
            markdown=markdown or body,
        )
        self._stream_plain = ""

    def format_all(self) -> str:
        parts: list[str] = []
        for e in self.entries:
            if e.kind == "user":
                parts.append(f"❯ {e.plain}")
            elif e.kind == "assistant":
                parts.append(e.plain)
            elif e.kind == "tool":
                head = f"⎿ {e.title or 'tool'}"
                parts.append(f"{head}\n{e.plain}")
            elif e.kind == "error":
                parts.append(f"Error: {e.plain}")
            else:
                parts.append(e.plain)
        return "\n\n".join(parts)

    def last_assistant(self) -> str | None:
        for e in reversed(self.entries):
            if e.kind == "assistant":
                return e.markdown or e.plain
        if self._stream_plain.strip():
            return self._stream_plain.strip()
        return None

    def last_tool(self) -> str | None:
        for e in reversed(self.entries):
            if e.kind == "tool":
                return e.plain
        return None

    def last_user(self) -> str | None:
        for e in reversed(self.entries):
            if e.kind == "user":
                return e.plain
        return None


def strip_rich_markup(text: str) -> str:
    return _RICH_TAG_RE.sub("", text).strip()


def plain_from_rich_write(content: Any) -> tuple[str, str | None]:
    """Derive (plain, markdown) from RichLog.write() content."""
    if content is None:
        return "", None
    if isinstance(content, str):
        if "[" in content and "]" in content:
            return strip_rich_markup(content), None
        return content.strip(), None
    markdown_src = getattr(content, "markup", None) or getattr(content, "source", None)
    if markdown_src and isinstance(markdown_src, str):
        return markdown_src.strip(), markdown_src.strip()
    try:
        from io import StringIO

        from rich.console import Console

        buf = StringIO()
        Console(file=buf, width=120, legacy_windows=False).print(content)
        plain = buf.getvalue().strip()
        return plain, markdown_src if isinstance(markdown_src, str) else None
    except Exception:
        return str(content).strip(), None