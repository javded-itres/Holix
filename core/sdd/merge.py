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


def _parse_delta_sections(delta: str) -> dict[str, list[_Requirement]]:
    """Return {ADDED|MODIFIED|REMOVED: [requirements]} from a delta spec."""
    sections: dict[str, list[_Requirement]] = {
        "ADDED": [],
        "MODIFIED": [],
        "REMOVED": [],
    }
    matches = list(_SECTION_RE.finditer(delta))
    if not matches:
        # Whole file treated as ADDED if it has requirements
        sections["ADDED"] = _split_requirements(delta)
        return sections

    for i, m in enumerate(matches):
        kind = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(delta)
        body = delta[start:end]
        sections[kind] = _split_requirements(body)
    return sections


def merge_delta_into_main(main_content: str, delta_content: str) -> str:
    """Apply delta requirement sections onto main spec markdown.

    - ADDED: append requirements not already present (by title)
    - MODIFIED: replace body of matching title
    - REMOVED: drop matching titles
    """
    preamble, main_reqs = _preamble_and_reqs(main_content)
    by_title: dict[str, _Requirement] = {
        _normalize_title(r.title): r for r in main_reqs
    }
    order = [_normalize_title(r.title) for r in main_reqs]

    sections = _parse_delta_sections(delta_content)

    for r in sections["REMOVED"]:
        key = _normalize_title(r.title)
        by_title.pop(key, None)
        order = [t for t in order if t != key]

    for r in sections["MODIFIED"]:
        key = _normalize_title(r.title)
        by_title[key] = r
        if key not in order:
            order.append(key)

    for r in sections["ADDED"]:
        key = _normalize_title(r.title)
        if key in by_title:
            # treat as modify if already exists
            by_title[key] = r
        else:
            by_title[key] = r
            order.append(key)

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
