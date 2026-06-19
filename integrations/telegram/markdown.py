"""Markdown / plain text → Telegram HTML (parse_mode=HTML)."""

from __future__ import annotations

import html
import re

# Fenced ```code``` blocks
_FENCE_RE = re.compile(r"```(?:[\w-]{0,32})?\s*\n?([\s\S]{0,8192}?)```")
# Rich markup leftovers
_RICH_TAG_RE = re.compile(r"\[/?[^\]]{0,256}\]")
_MAX_REGEX_SCAN = 500
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_BULLET_RE = re.compile(r"^[-*•]\s+(.+)$")
_ORDERED_RE = re.compile(r"^\d+\.\s+(.+)$")


def escape_html(text: str) -> str:
    return html.escape(text or "", quote=False)


def _strip_rich_markup(text: str) -> str:
    return _RICH_TAG_RE.sub("", text or "")


_INLINE_PATTERN = re.compile(
    r"`([^`\n]+)`|"
    r"\[([^\]]+)\]\(([^)]+)\)|"
    r"\*\*(.+?)\*\*|"
    r"__(.+?)__|"
    r"(?<!\*)\*([^*\n]+)\*(?!\*)|"
    r"(?<!_)_([^_\n]+)_(?!_)"
)


def _apply_inline_styles(text: str) -> str:
    """Bold, italic, code, links on a single line (no block fences)."""
    if not text:
        return ""

    parts: list[str] = []
    last = 0
    for index, match in enumerate(_INLINE_PATTERN.finditer(text)):
        if index >= _MAX_REGEX_SCAN:
            break
        parts.append(escape_html(text[last : match.start()]))
        if match.group(1) is not None:
            parts.append(f"<code>{escape_html(match.group(1))}</code>")
        elif match.group(2) is not None:
            url = escape_html(match.group(3).strip())
            label = escape_html(match.group(2))
            parts.append(f'<a href="{url}">{label}</a>')
        elif match.group(4) is not None:
            parts.append(f"<b>{escape_html(match.group(4))}</b>")
        elif match.group(5) is not None:
            parts.append(f"<b>{escape_html(match.group(5))}</b>")
        elif match.group(6) is not None:
            parts.append(f"<i>{escape_html(match.group(6))}</i>")
        elif match.group(7) is not None:
            parts.append(f"<i>{escape_html(match.group(7))}</i>")
        last = match.end()
    parts.append(escape_html(text[last:]))
    return "".join(parts)


def _format_block_segment(text: str) -> str:
    """Paragraphs, headings, lists — no fenced code."""
    text = _strip_rich_markup(text)
    lines_out: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            lines_out.append("")
            continue
        stripped = line.strip()
        hm = _HEADER_RE.match(stripped)
        if hm:
            lines_out.append(f"<b>{escape_html(hm.group(2))}</b>")
            continue
        bm = _BULLET_RE.match(stripped)
        if bm:
            lines_out.append(f"• {_apply_inline_styles(bm.group(1))}")
            continue
        om = _ORDERED_RE.match(stripped)
        if om:
            lines_out.append(f"• {_apply_inline_styles(om.group(1))}")
            continue
        lines_out.append(_apply_inline_styles(line))
    return "\n".join(lines_out)


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown-ish assistant text to Telegram HTML."""
    raw = _strip_rich_markup(text or "")
    if not raw.strip():
        return ""

    parts: list[str] = []
    last = 0
    for index, match in enumerate(_FENCE_RE.finditer(raw)):
        if index >= _MAX_REGEX_SCAN:
            break
        before = raw[last : match.start()]
        if before.strip():
            parts.append(_format_block_segment(before))
        code = match.group(1).strip("\n")
        if code:
            parts.append(f"<pre>{escape_html(code)}</pre>")
        last = match.end()

    tail = raw[last:]
    if tail.strip():
        parts.append(_format_block_segment(tail))

    return "\n\n".join(p for p in parts if p)


def plain_to_telegram_html(text: str) -> str:
    """Format arbitrary text; uses Markdown HTML (not a single <pre> block)."""
    converted = markdown_to_telegram_html(text)
    if converted:
        return converted
    return escape_html(text or "")


_TELEGRAM_TAG_RE = re.compile(
    r"<(/?)([a-z]{1,32})(?:\s[^>\n]{0,512})?>",
    re.IGNORECASE,
)
_VOID_TAGS = frozenset({"br", "hr", "img"})
_TELEGRAM_MAX_LEN = 4090


def truncate_telegram_html(html: str, max_len: int = _TELEGRAM_MAX_LEN) -> str:
    """Truncate HTML without breaking Telegram parse_mode (closes open tags)."""
    text = html or ""
    if len(text) <= max_len:
        return text

    cut = text[:max_len]
    if cut.rfind("<") > cut.rfind(">"):
        cut = cut[: cut.rfind("<")]

    def _open_tags(fragment: str) -> list[str]:
        stack: list[str] = []
        for index, match in enumerate(_TELEGRAM_TAG_RE.finditer(fragment)):
            if index >= _MAX_REGEX_SCAN:
                break
            closing, tag = match.group(1), match.group(2).lower()
            if tag in _VOID_TAGS:
                continue
            if closing:
                if stack and stack[-1] == tag:
                    stack.pop()
            else:
                stack.append(tag)
        return stack

    stack = _open_tags(cut)
    suffix = "".join(f"</{tag}>" for tag in reversed(stack))
    room = max_len - len(suffix)
    if room < 1:
        return escape_html(text[: max_len - 1]) + "…"

    if len(cut) > room:
        cut = cut[:room]
        if cut.rfind("<") > cut.rfind(">"):
            cut = cut[: cut.rfind("<")]
        stack = _open_tags(cut)
        suffix = "".join(f"</{tag}>" for tag in reversed(stack))

    result = cut + suffix
    if len(result) <= max_len:
        return result
    return truncate_telegram_html(cut[: max(1, room - 4)] + "…", max_len)


def split_telegram_html(html: str, max_len: int = _TELEGRAM_MAX_LEN) -> list[str]:
    """Split rendered Telegram HTML into chunks each <= max_len.

    Tries to split on natural boundaries (double newlines, after code blocks)
    to keep messages readable. Falls back to character-based with tag repair.
    """
    text = html or ""
    if len(text) <= max_len:
        return [text] if text.strip() else []

    chunks: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        # take up to max
        end = min(pos + max_len, n)
        candidate = text[pos:end]

        if end < n:
            # prefer breaking at good points: after </pre>, double \n, single \n, sentence, space
            for marker in ["</pre>\n\n", "</pre>", "\n\n", "\n", ". ", " "]:
                idx = candidate.rfind(marker)
                if idx >= int(max_len * 0.55):  # avoid tiny chunks
                    cut_at = idx + len(marker)
                    candidate = candidate[:cut_at]
                    end = pos + cut_at
                    break

        # repair tags and length via existing truncate helper
        chunk = truncate_telegram_html(candidate, max_len)
        if chunk.strip():
            chunks.append(chunk)

        pos = end
        # skip leading whitespace for next chunk
        while pos < n and text[pos].isspace():
            pos += 1

        if pos >= n:
            break

    # de-dupe empties
    return [c for c in chunks if c.strip()]