"""Per-conversation memory of URLs already fetched this session."""

from __future__ import annotations

import threading
from urllib.parse import urlsplit, urlunsplit

_LOCK = threading.Lock()
# conversation_id → {normalized_url: (status, excerpt)}
_FETCHES: dict[str, dict[str, tuple[int, str]]] = {}
_MAX_URLS_PER_CONVERSATION = 64


def normalize_fetch_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = (parts.netloc or "").lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def remember_fetch(conversation_id: str, url: str, status: int, excerpt: str = "") -> None:
    cid = (conversation_id or "default").strip() or "default"
    key = normalize_fetch_url(url)
    if not key:
        return
    snippet = (excerpt or "").strip()[:400]
    with _LOCK:
        bucket = _FETCHES.setdefault(cid, {})
        if key not in bucket and len(bucket) >= _MAX_URLS_PER_CONVERSATION:
            # drop an arbitrary oldest-inserted key (CPython 3.7+ insertion order)
            bucket.pop(next(iter(bucket)))
        bucket[key] = (int(status), snippet)


def lookup_fetch(conversation_id: str, url: str) -> tuple[int, str] | None:
    cid = (conversation_id or "default").strip() or "default"
    key = normalize_fetch_url(url)
    if not key:
        return None
    with _LOCK:
        hit = _FETCHES.get(cid, {}).get(key)
    return hit


def already_fetched_message(url: str, status: int, excerpt: str = "") -> str:
    extra = ""
    if status in {404, 403, 410}:
        extra = (
            " That URL failed last time. Do not guess sibling paths; "
            "answer from pages that already succeeded in this session."
        )
    body = (excerpt or "").strip()
    tail = f"\n\n{body}" if body else ""
    return (
        f"Already fetched this URL in this conversation (HTTP {status}). "
        f"Do not refetch — use the earlier result in this session.{extra}{tail}"
    )


def reset_fetch_memory(conversation_id: str | None = None) -> None:
    with _LOCK:
        if conversation_id is None:
            _FETCHES.clear()
            return
        cid = (conversation_id or "default").strip() or "default"
        _FETCHES.pop(cid, None)
