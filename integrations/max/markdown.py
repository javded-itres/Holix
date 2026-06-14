"""Text chunking and Markdown → HTML for MAX messages."""

from __future__ import annotations

import html
import re

MAX_MESSAGE_LEN = 4000
SAFE_CHUNK_LEN = 3900

_FENCE_RE = re.compile(r"```(?:[\w-]+)?\s*\n?([\s\S]*?)```")
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^[-*•]\s+(.+)$", re.MULTILINE)
_ORDERED_RE = re.compile(r"^\d+\.\s+(.+)$", re.MULTILINE)
_RICH_TAG_RE = re.compile(r"\[/?[^\]]+\]")
_MARKDOWN_HINT_RE = re.compile(
    r"(?:"
    r"\*\*.+?\*\*|__.+?__|"
    r"(?<![*_`])_.+?_(?![*_`])|"
    r"`[^`\n]+`|"
    r"\[[^\]]+\]\([^)]+\)|"
    r"^#{1,6}\s|"
    r"^>\s|"
    r"^\s*[-*•]\s|"
    r"^\d+\.\s|"
    r"~~.+?~~|"
    r"\+\+.+?\+\+"
    r")",
    re.MULTILINE,
)
_HTML_TAG_RE = re.compile(r"<(/?)([a-z]+)(?:\s[^>]*)?>", re.IGNORECASE)
_VOID_TAGS = frozenset({"br", "hr", "img"})

_INLINE_PATTERN = re.compile(
    r"`([^`\n]+)`|"
    r"\[([^\]]+)\]\(([^)]+)\)|"
    r"\*\*(.+?)\*\*|"
    r"__(.+?)__|"
    r"(?<!\*)\*([^*\n]+)\*(?!\*)|"
    r"(?<!_)_([^_\n]+)_(?!_)"
)


def escape_html(text: str) -> str:
    return html.escape(text or "", quote=False)


def truncate_max_text(text: str, *, limit: int = SAFE_CHUNK_LEN) -> str:
    raw = (text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: limit - 1] + "…"


def split_max_text(text: str, *, limit: int = SAFE_CHUNK_LEN) -> list[str]:
    raw = text or ""
    if not raw.strip():
        return []
    if len(raw) <= limit:
        return [raw]
    chunks: list[str] = []
    start = 0
    while start < len(raw):
        end = min(start + limit, len(raw))
        if end < len(raw):
            break_at = raw.rfind("\n\n", start, end)
            if break_at <= start:
                break_at = raw.rfind("\n", start, end)
            if break_at > start:
                end = break_at
        piece = raw[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end if end > start else start + limit
    return chunks or [truncate_max_text(raw)]


def _strip_rich_markup(text: str) -> str:
    return _RICH_TAG_RE.sub("", text or "")


def _apply_inline_styles(text: str) -> str:
    if not text:
        return ""

    parts: list[str] = []
    last = 0
    for match in _INLINE_PATTERN.finditer(text):
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
    text = _strip_rich_markup(text)
    lines_out: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            lines_out.append("")
            continue
        stripped = line.strip()
        if stripped.startswith("> "):
            lines_out.append(f"<blockquote>{_apply_inline_styles(stripped[2:])}</blockquote>")
            continue
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


def markdown_to_max_html(text: str) -> str:
    """Convert Markdown-ish assistant text to MAX HTML."""
    raw = _strip_rich_markup(text or "")
    if not raw.strip():
        return ""

    parts: list[str] = []
    last = 0
    for match in _FENCE_RE.finditer(raw):
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


def plain_to_max_html(text: str) -> str:
    """Format arbitrary text as MAX HTML (not a single <pre> block)."""
    converted = markdown_to_max_html(text)
    if converted:
        return converted
    return escape_html(text or "")


def truncate_max_html(html_text: str, max_len: int = SAFE_CHUNK_LEN) -> str:
    """Truncate HTML without breaking MAX format (closes open tags)."""
    text = html_text or ""
    if len(text) <= max_len:
        return text

    cut = text[:max_len]
    if cut.rfind("<") > cut.rfind(">"):
        cut = cut[: cut.rfind("<")]

    stack: list[str] = []
    for match in _HTML_TAG_RE.finditer(cut):
        closing, tag = match.group(1), match.group(2).lower()
        if tag in _VOID_TAGS:
            continue
        if closing:
            if stack and stack[-1] == tag:
                stack.pop()
        else:
            stack.append(tag)

    suffix = "".join(f"</{tag}>" for tag in reversed(stack))
    room = max_len - len(suffix)
    if room < 1:
        return escape_html(text[: max_len - 1]) + "…"

    if len(cut) > room:
        cut = cut[:room]
        if cut.rfind("<") > cut.rfind(">"):
            cut = cut[: cut.rfind("<")]
        stack = []
        for match in _HTML_TAG_RE.finditer(cut):
            closing, tag = match.group(1), match.group(2).lower()
            if tag in _VOID_TAGS:
                continue
            if closing:
                if stack and stack[-1] == tag:
                    stack.pop()
            else:
                stack.append(tag)
        suffix = "".join(f"</{tag}>" for tag in reversed(stack))

    result = cut + suffix
    if len(result) <= max_len:
        return result
    return truncate_max_html(cut[: max(1, room - 4)] + "…", max_len)


def split_max_html(html_text: str, max_len: int = SAFE_CHUNK_LEN) -> list[str]:
    """Split rendered MAX HTML into chunks each <= max_len."""
    text = html_text or ""
    if len(text) <= max_len:
        return [text] if text.strip() else []

    chunks: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        end = min(pos + max_len, n)
        candidate = text[pos:end]

        if end < n:
            for marker in ["</pre>\n\n", "</pre>", "\n\n", "\n", ". ", " "]:
                idx = candidate.rfind(marker)
                if idx >= int(max_len * 0.55):
                    cut_at = idx + len(marker)
                    candidate = candidate[:cut_at]
                    end = pos + cut_at
                    break

        chunk = truncate_max_html(candidate, max_len)
        if chunk.strip():
            chunks.append(chunk)

        pos = end
        while pos < n and text[pos].isspace():
            pos += 1

        if pos >= n:
            break

    return [c for c in chunks if c.strip()]


def prepare_max_html(text: str) -> str:
    """Convert assistant text to MAX HTML for ``format=html`` messages."""
    return truncate_max_html(plain_to_max_html(text))


def looks_like_markdown(text: str) -> bool:
    """Heuristic: does this message contain Markdown formatting?"""
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(_MARKDOWN_HINT_RE.search(raw))


def _normalize_headers(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        title = match.group(2).strip()
        return f"# {title}" if title else ""

    return _HEADER_RE.sub(repl, text)


def _normalize_fenced_code(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        code = (match.group(1) or "").strip("\n")
        if not code:
            return ""
        lines = code.split("\n")
        if len(lines) == 1:
            return f"`{lines[0]}`"
        quoted = "\n".join(f"> {line}" if line else ">" for line in lines)
        return f"**Код:**\n{quoted}"

    return _FENCE_RE.sub(repl, text)


def prepare_max_markdown(text: str) -> str:
    """Legacy Markdown normalization (prefer :func:`prepare_max_html`)."""
    raw = _strip_rich_markup(text or "").strip()
    if not raw:
        return ""
    raw = _normalize_fenced_code(raw)
    raw = _normalize_headers(raw)
    return truncate_max_text(raw)