"""Clickable file/http links for generate_image / generate_video tool results."""

from __future__ import annotations

import re
from pathlib import Path

MEDIA_TOOL_NAMES = frozenset({"generate_image", "generate_video"})

_FILE_URI_RE = re.compile(r"file://[^\s)\]>]+")
_HTTP_URI_RE = re.compile(r"https?://[^\s)\]>]+")
_SAVED_RE = re.compile(
    r"Saved (?:image|video):\s+(\S+)",
    re.IGNORECASE,
)
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\((file://[^)]+|https?://[^)]+)\)")


def path_to_file_uri(path: str) -> str:
    raw = (path or "").strip().strip("`")
    if raw.startswith("file:"):
        return raw
    return Path(raw).expanduser().resolve().as_uri()


def extract_media_hrefs(body: str) -> list[str]:
    """file:// first, then http(s), unique, stable order."""
    text = body or ""
    found: list[str] = []
    seen: set[str] = set()

    def _add(href: str) -> None:
        h = href.rstrip(".,;")
        if h and h not in seen:
            seen.add(h)
            found.append(h)

    for m in _MD_LINK_RE.finditer(text):
        _add(m.group(1))
    for m in _FILE_URI_RE.finditer(text):
        _add(m.group(0))
    for m in _SAVED_RE.finditer(text):
        _add(path_to_file_uri(m.group(1)))
    for m in _HTTP_URI_RE.finditer(text):
        _add(m.group(0))
    return found


def format_media_tool_result(body: str, *, tool_name: str = ""):
    """Rich renderable: dim summary + clickable Open link."""
    from rich.text import Text

    hrefs = extract_media_hrefs(body)
    kind = "video" if "video" in (tool_name or "") else "image"
    label = "Open video" if kind == "video" else "Open image"
    text = Text()
    if hrefs:
        first = hrefs[0]
        text.append("  ")
        text.append(label, style=f"bold underline link {first}")
        text.append("  ", style="dim")
        text.append(first, style=f"dim underline link {first}")
        for extra in hrefs[1:]:
            text.append("\n  ", style="dim")
            text.append(extra, style=f"dim underline link {extra}")
        return text
    preview = (body or "").strip().replace("\n", " ")
    if len(preview) > 400:
        preview = preview[:400] + "…"
    return Text(f"  {preview}", style="dim")


def open_media_href(href: str) -> bool:
    """Open file:// or http(s) with the OS handler. Returns True if launched."""
    import os
    import subprocess
    import sys
    import webbrowser

    url = (href or "").strip()
    if not url:
        return False
    try:
        if url.startswith("file:"):
            from urllib.parse import unquote, urlparse

            parsed = urlparse(url)
            path = Path(unquote(parsed.path or ""))
            if sys.platform == "darwin":
                subprocess.Popen(
                    ["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            elif sys.platform.startswith("linux"):
                subprocess.Popen(
                    ["xdg-open", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
                )
            else:
                webbrowser.open(url)
            return True
        webbrowser.open(url)
        return True
    except Exception:
        return False
