"""Show what an archive will change, and what it will drop."""

from __future__ import annotations

import difflib
import re

from core.sdd.merge import (
    _is_stub_requirement,
    _normalize_title,
    _parse_delta_sections,
    _preamble_and_reqs,
)

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_DELTA_SECTION_RE = re.compile(r"(?i)^(ADDED|MODIFIED|REMOVED)\s+Requirements?$")
_SCENARIO_RE = re.compile(r"^####\s+(.+?)\s*$", re.MULTILINE)
_REASON_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(?:reason|migration|причина|миграция)(?:\*\*)?\s*:\s*(.+)$"
)
_DIFF_LIMIT = 2000


def titles_collide(left: str, right: str) -> bool:
    """True when two titles match ignoring case and differ only by case."""
    a = re.sub(r"\s+", " ", (left or "").strip())
    b = re.sub(r"\s+", " ", (right or "").strip())
    if not a or not b or a == b:
        return False
    return a.casefold() == b.casefold()


def _clip(text: str, limit: int = _DIFF_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… (truncated)"


def _scenarios(body: str) -> list[str]:
    names: list[str] = []
    for match in _SCENARIO_RE.finditer(body or ""):
        name = re.sub(r"(?i)^scenario:\s*", "", match.group(1).strip()).strip()
        if name:
            names.append(name)
    return names


def _reason_lines(body: str) -> str:
    found = [m.group(1).strip() for m in _REASON_RE.finditer(body or "")]
    return "; ".join(found)


def _unified(old: str, new: str, title: str) -> str:
    diff = "".join(
        difflib.unified_diff(
            (old or "").splitlines(keepends=True),
            (new or "").splitlines(keepends=True),
            fromfile=f"main:{title}",
            tofile=f"delta:{title}",
            n=2,
        )
    )
    return _clip(diff)


def _dropped_text(delta: str) -> list[str]:
    """Prose and extra headings archive does not copy into the main spec."""
    text = delta or ""
    dropped: list[str] = []
    sections = list(_H2_RE.finditer(text))
    delta_sections = [m for m in sections if _DELTA_SECTION_RE.match(m.group(1).strip())]
    if delta_sections:
        preamble = text[: delta_sections[0].start()]
    else:
        preamble = text
    preamble_lines: list[str] = []
    for line in preamble.splitlines():
        stripped = line.strip()
        if not stripped or (stripped.startswith("# ") and not stripped.startswith("##")):
            continue
        preamble_lines.append(stripped)
    if preamble_lines:
        dropped.append(_clip("\n".join(preamble_lines), 400))
    for match in sections:
        heading = match.group(1).strip()
        if _DELTA_SECTION_RE.match(heading):
            continue
        dropped.append(f"## {heading}")
    return dropped


def review_delta(main: str, delta: str, *, domain: str = "") -> dict:
    """Per-requirement diff plus warnings for text archive would lose."""
    warnings: list[str] = []
    errors: list[str] = []
    requirements: list[dict] = []
    _preamble, main_reqs = _preamble_and_reqs(main or "")
    by_key = {_normalize_title(req.title): req for req in main_reqs}
    seen_titles: list[str] = [req.title for req in main_reqs]

    for kind, reqs in _parse_delta_sections(delta or ""):
        for req in reqs:
            if _is_stub_requirement(req):
                continue
            for previous in seen_titles:
                if titles_collide(previous, req.title):
                    errors.append(
                        f"{domain or 'spec'}: requirement titles differ only by case: "
                        f"{previous!r} and {req.title!r}"
                    )
            seen_titles.append(req.title)
            key = _normalize_title(req.title)
            current = by_key.get(key)
            entry: dict = {
                "domain": domain,
                "op": kind,
                "title": req.title,
            }
            if kind == "REMOVED":
                entry["reason"] = _reason_lines(req.body)
                if current is None:
                    warnings.append(
                        f"{domain or 'spec'}: REMOVED {req.title!r} is not in the main spec"
                    )
            elif kind == "MODIFIED" and current is not None:
                before = _scenarios(current.body)
                after = _scenarios(req.body)
                after_keys = {name.casefold() for name in after}
                lost = [name for name in before if name.casefold() not in after_keys]
                entry["diff"] = _unified(current.body, req.body, req.title)
                entry["scenarios_lost"] = lost
                if lost:
                    warnings.append(
                        f"{domain or 'spec'}: MODIFIED {req.title!r} drops scenario(s): "
                        + ", ".join(lost)
                    )
            elif kind == "MODIFIED":
                entry["appended"] = True
                entry["text"] = _clip(req.body.strip())
                warnings.append(
                    f"{domain or 'spec'}: MODIFIED {req.title!r} is not in the main spec; "
                    "archive will add it"
                )
            else:
                entry["text"] = _clip(req.body.strip())
            requirements.append(entry)
            if kind == "REMOVED":
                by_key.pop(key, None)
            else:
                by_key[key] = req

    dropped = _dropped_text(delta or "")
    for chunk in dropped:
        first = chunk.splitlines()[0][:120]
        warnings.append(f"{domain or 'spec'}: archive will not merge: {first}")

    # Same error can fire against several earlier titles; keep the first of each.
    unique_errors: list[str] = []
    for err in errors:
        if err not in unique_errors:
            unique_errors.append(err)
    return {
        "warnings": warnings,
        "errors": unique_errors,
        "requirements": requirements,
        "dropped": dropped,
    }
