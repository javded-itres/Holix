"""First-pass review of long-term facts: what to keep, forget, or rewrite.

The agent adds its own judgment on top of these flags. Nothing here deletes
a row; the user confirms that in ``review_memory``.
"""

from __future__ import annotations

import re
from typing import Any

_STALE = (
    "временно",
    "temporary",
    "todo",
    "на сегодня",
    "this session",
    "одноразово",
    "устарело",
    "outdated",
    "больше не",
    "no longer",
)
_NEG = re.compile(
    r"(?<![a-zа-я])(not|no|never|не|нет)(?![a-zа-я])|n't|больше не|no longer",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-zа-я0-9]{4,}", re.IGNORECASE)
_STEM_TAIL = re.compile(r"(_old|_new|_2|\d+)$", re.IGNORECASE)


def normalize_fact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def analyze_memory_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the same items with ``suggestion`` and ``reason``.

    ``suggestion`` is ``keep``, ``forget``, or ``revise``. Newer ``updated_at``
    wins when two rows say the same thing or contradict each other.
    """
    prepared = [_copy_item(item) for item in items if str(item.get("key") or "").strip()]
    for item in prepared:
        if not str(item.get("content") or "").strip():
            _mark(item, "forget", "empty")

    by_text: dict[str, list[dict[str, Any]]] = {}
    for item in prepared:
        if item.get("suggestion"):
            continue
        by_text.setdefault(normalize_fact(str(item.get("content") or "")), []).append(item)
    for group in by_text.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=_recency, reverse=True)
        keeper = ordered[0]
        for older in ordered[1:]:
            _mark(older, "forget", f"duplicate of {keeper['key']}")

    by_stem: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in prepared:
        if item.get("suggestion"):
            continue
        stem = _stem(str(item["key"]))
        # Numeric episode ids share an empty stem and are not rewrites of each other.
        if not stem:
            continue
        by_stem.setdefault((str(item["kind"]), stem), []).append(item)
    for group in by_stem.values():
        contents = {normalize_fact(str(item.get("content") or "")) for item in group}
        if len(group) < 2 or len(contents) < 2:
            continue
        ordered = sorted(group, key=_recency, reverse=True)
        keeper = ordered[0]
        for older in ordered[1:]:
            _mark(older, "revise", f"older value; newer is {keeper['key']}")

    open_items = [item for item in prepared if not item.get("suggestion")]
    for index, left in enumerate(open_items):
        for right in open_items[index + 1 :]:
            if left.get("suggestion") and right.get("suggestion"):
                continue
            if not _contradicts(left, right):
                continue
            newer, older = sorted((left, right), key=_recency, reverse=True)
            if not older.get("suggestion"):
                _mark(older, "forget", f"contradicts {newer['key']}")

    for item in prepared:
        if item.get("suggestion"):
            continue
        content = str(item.get("content") or "").lower()
        if any(phrase in content for phrase in _STALE):
            _mark(item, "forget", "looks temporary or already outdated")
            continue
        _mark(item, "keep", "no conflict found")
    return prepared


def _copy_item(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out["kind"] = str(item.get("kind") or "semantic")
    out["key"] = str(item.get("key") or "").strip()
    out["content"] = str(item.get("content") or "")
    out["updated_at"] = str(item.get("updated_at") or "")
    out.pop("suggestion", None)
    out.pop("reason", None)
    return out


def _mark(item: dict[str, Any], suggestion: str, reason: str) -> None:
    item["suggestion"] = suggestion
    item["reason"] = reason


def _recency(item: dict[str, Any]) -> str:
    return str(item.get("updated_at") or "")


def _stem(key: str) -> str:
    return _STEM_TAIL.sub("", key.lower())


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _WORD.finditer(text or "")}


def _contradicts(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a = _tokens(str(left.get("content") or ""))
    b = _tokens(str(right.get("content") or ""))
    if not a or not b:
        return False
    overlap = len(a & b) / len(a | b)
    if overlap < 0.55:
        return False
    neg_a = bool(_NEG.search(str(left.get("content") or "")))
    neg_b = bool(_NEG.search(str(right.get("content") or "")))
    return neg_a != neg_b
