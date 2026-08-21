"""Merge delta specs (ADDED/MODIFIED/REMOVED) into main domain specs."""

from __future__ import annotations

import re
from dataclasses import dataclass

_REQ_HEADER_RE = re.compile(
    r"^(#{1,6})\s+Requirement:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_SECTION_RE = re.compile(
    r"^##\s+(ADDED|MODIFIED|REMOVED)\s+Requirements?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class _Requirement:
    title: str
    body: str  # includes heading line


def _split_requirements(content: str) -> list[_Requirement]:
    """Split a spec document into Requirement blocks (by heading)."""
    matches = list(_REQ_HEADER_RE.finditer(content))
    if not matches:
        return []
    reqs: list[_Requirement] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end].rstrip() + "\n"
        title = m.group(2).strip()
        reqs.append(_Requirement(title=title, body=block))
    return reqs


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def _preamble_and_reqs(content: str) -> tuple[str, list[_Requirement]]:
    matches = list(_REQ_HEADER_RE.finditer(content))
    if not matches:
        return content.rstrip() + ("\n" if content.strip() else ""), []
    preamble = content[: matches[0].start()].rstrip()
    return preamble, _split_requirements(content)


def _parse_delta_sections(delta: str) -> list[tuple[str, list[_Requirement]]]:
    """Return ordered [(ADDED|MODIFIED|REMOVED, requirements), ...] from a delta.

    Sections are applied in document order so a later REMOVED wins over an
    earlier MODIFIED of the same title (and vice versa).
    """
    matches = list(_SECTION_RE.finditer(delta))
    if not matches:
        # Whole file treated as ADDED if it has requirements
        return [("ADDED", _split_requirements(delta))]

    ordered: list[tuple[str, list[_Requirement]]] = []
    for i, m in enumerate(matches):
        kind = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(delta)
        body = delta[start:end]
        ordered.append((kind, _split_requirements(body)))
    return ordered


def _apply_section(
    *,
    kind: str,
    reqs: list[_Requirement],
    by_title: dict[str, _Requirement],
    order: list[str],
) -> list[str]:
    """Mutate by_title; return updated order of normalized titles."""
    if kind == "REMOVED":
        for r in reqs:
            key = _normalize_title(r.title)
            by_title.pop(key, None)
            order = [t for t in order if t != key]
        return order

    if kind == "MODIFIED":
        for r in reqs:
            key = _normalize_title(r.title)
            by_title[key] = r
            if key not in order:
                order.append(key)
        return order

    # ADDED (and unknown kinds treated as ADDED)
    for r in reqs:
        key = _normalize_title(r.title)
        if key in by_title:
            # Already present → replace body (safe re-archive / re-add)
            by_title[key] = r
        else:
            by_title[key] = r
            order.append(key)
    return order


def count_delta_requirements(delta_content: str) -> int:
    """How many Requirement blocks the delta will attempt to apply."""
    return sum(len(reqs) for _, reqs in _parse_delta_sections(delta_content or ""))


def merge_delta_into_main(main_content: str, delta_content: str) -> str:
    """Apply delta requirement sections onto main spec markdown.

    - ADDED: append requirements not already present (by title); if title exists, replace body
    - MODIFIED: replace body of matching title (append if missing)
    - REMOVED: drop matching titles
    - Sections are applied **in document order** (later section wins for the same title)
    - Duplicate titles in main are collapsed to a single requirement
    """
    preamble, main_reqs = _preamble_and_reqs(main_content)
    by_title: dict[str, _Requirement] = {}
    order: list[str] = []
    for r in main_reqs:
        key = _normalize_title(r.title)
        by_title[key] = r
        if key not in order:
            order.append(key)

    for kind, reqs in _parse_delta_sections(delta_content):
        order = _apply_section(kind=kind, reqs=reqs, by_title=by_title, order=order)

    parts: list[str] = []
    if preamble.strip():
        parts.append(preamble.rstrip())
        parts.append("")
    for key in order:
        req = by_title.get(key)
        if req:
            parts.append(req.body.rstrip())
            parts.append("")

    result = "\n".join(parts).rstrip() + "\n"
    return result


_STUB_MARKERS = (
    "The system SHALL …",
    "The system SHALL ...",
    "- **GIVEN** …",
    "- **GIVEN** ...",
    "<!-- fill after understanding confirmed -->",
)


def normalize_delta_op(op: str) -> str:
    raw = (op or "").strip().lower()
    if raw in {"add", "added", "create", "new", "+"}:
        return "ADDED"
    if raw in {"modify", "modified", "change", "update", "patch", "~"}:
        return "MODIFIED"
    if raw in {"remove", "removed", "delete", "drop", "-"}:
        return "REMOVED"
    raise ValueError(f"unknown op {op!r}; use add | modify | remove (ADDED/MODIFIED/REMOVED)")


def _is_stub_requirement(req: _Requirement) -> bool:
    return any(m in req.body for m in _STUB_MARKERS)


def _make_requirement(title: str, body: str) -> _Requirement:
    title = (title or "").strip()
    text = (body or "").strip()
    first = text.split("\n", 1)[0] if text else ""
    if first and _REQ_HEADER_RE.match(first):
        m = _REQ_HEADER_RE.match(first)
        if m:
            title = m.group(2).strip() or title
        return _Requirement(title=title, body=text.rstrip() + "\n")
    if not title:
        raise ValueError("requirement title is required")
    heading = f"### Requirement: {title}\n"
    rest = text + ("\n" if text and not text.endswith("\n") else "")
    block = heading + (("\n" + rest) if rest else "\n")
    return _Requirement(title=title, body=block)


def _delta_preamble(delta: str) -> str:
    m = _SECTION_RE.search(delta or "")
    if m:
        return delta[: m.start()].rstrip()
    matches = list(_REQ_HEADER_RE.finditer(delta or ""))
    if matches:
        return delta[: matches[0].start()].rstrip()
    return (delta or "").rstrip()


def _load_delta_buckets(
    delta: str,
) -> tuple[str, dict[str, list[_Requirement]]]:
    preamble = _delta_preamble(delta or "")
    buckets: dict[str, list[_Requirement]] = {
        "ADDED": [],
        "MODIFIED": [],
        "REMOVED": [],
    }
    for kind, reqs in _parse_delta_sections(delta or ""):
        key_kind = kind if kind in buckets else "ADDED"
        for r in reqs:
            nk = _normalize_title(r.title)
            for name in list(buckets):
                buckets[name] = [x for x in buckets[name] if _normalize_title(x.title) != nk]
            buckets[key_kind].append(r)
    return preamble, buckets


def _serialize_delta(
    preamble: str,
    buckets: dict[str, list[_Requirement]],
) -> str:
    parts: list[str] = []
    if (preamble or "").strip():
        parts.append(preamble.rstrip())
        parts.append("")
    for kind in ("ADDED", "MODIFIED", "REMOVED"):
        reqs = buckets.get(kind) or []
        if not reqs:
            continue
        parts.append(f"## {kind} Requirements")
        parts.append("")
        for r in reqs:
            parts.append(r.body.rstrip())
            parts.append("")
    text = "\n".join(parts).rstrip()
    return (text + "\n") if text else ""


def patch_delta_spec(
    existing: str,
    *,
    op: str,
    title: str,
    body: str = "",
) -> str:
    """Patch one requirement into a change delta spec (ADDED/MODIFIED/REMOVED)."""
    kind = normalize_delta_op(op)
    req = _make_requirement(title, body)
    preamble, buckets = _load_delta_buckets(existing or "")
    key = _normalize_title(req.title)
    was_added = any(_normalize_title(r.title) == key for r in buckets["ADDED"])
    for name in list(buckets):
        buckets[name] = [x for x in buckets[name] if _normalize_title(x.title) != key]
    if kind == "ADDED":
        buckets["ADDED"] = [r for r in buckets["ADDED"] if not _is_stub_requirement(r)]
        buckets["ADDED"].append(req)
    elif kind == "MODIFIED":
        if was_added:
            buckets["ADDED"].append(req)
        else:
            buckets["MODIFIED"].append(req)
    else:
        if not was_added:
            buckets["REMOVED"].append(req)
    return _serialize_delta(preamble, buckets)


def merge_delta_patches(base_delta: str, patch_delta: str) -> str:
    """Apply a delta snippet onto an existing change delta document."""
    result = base_delta or ""
    for kind, reqs in _parse_delta_sections(patch_delta or ""):
        for r in reqs:
            body = r.body
            # Avoid doubling the heading inside patch_delta_spec.
            result = patch_delta_spec(result, op=kind, title=r.title, body=body)
    return result
