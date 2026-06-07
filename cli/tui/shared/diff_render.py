"""GitHub-style unified diff rendering for TUI transcripts."""

from __future__ import annotations

import re
from typing import Iterable

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def _diff_stats(lines: Iterable[str]) -> tuple[int, int]:
    added = removed = 0
    for line in lines:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _format_title(path: str, added: int, removed: int) -> Text:
    title = Text()
    if path:
        title.append(path, style="bold cyan")
    else:
        title.append("changes", style="bold")
    if added or removed:
        title.append("  ")
        if added:
            title.append(f"+{added}", style="bold green")
        if added and removed:
            title.append("  ")
        if removed:
            title.append(f"−{removed}", style="bold red")
    return title


def _render_hunk_header(line: str) -> Text:
    m = _HUNK_RE.match(line)
    row = Text()
    row.append("    ", style="dim")
    if m:
        old_start, old_len, new_start, new_len, rest = m.groups()
        old_len = old_len or "1"
        new_len = new_len or "1"
        row.append(f"@@ −{old_start},{old_len} ", style="dim")
        row.append(f"+{new_start},{new_len}", style="bold cyan")
        row.append(" @@", style="bold cyan")
        if rest:
            row.append(rest, style="italic dim")
    else:
        row.append(line, style="bold cyan")
    return row


def _line_no(n: int | None) -> str:
    return f"{n:>4} " if n is not None else "     "


def _render_diff_line(line: str, *, old_no: int | None, new_no: int | None) -> Text:
    if line.startswith("+++") or line.startswith("---"):
        row = Text()
        row.append("      ", style="dim")
        row.append(line, style="bold dim")
        return row

    if line.startswith("@@"):
        return _render_hunk_header(line)

    sign = line[:1]
    body = line[1:] if line[:1] in "+- " else line
    if not body:
        body = " "

    if sign == "+":
        row = Text()
        row.append(_line_no(None), style="dim on grey15")
        row.append(_line_no(new_no), style="bold green on grey15")
        row.append("│ + ", style="bold green on grey15")
        row.append(body, style="green on grey15")
        return row

    if sign == "-":
        row = Text()
        row.append(_line_no(old_no), style="bold red on grey15")
        row.append(_line_no(None), style="dim on grey15")
        row.append("│ − ", style="bold red on grey15")
        row.append(body, style="red on grey15")
        return row

    row = Text()
    row.append(_line_no(old_no), style="dim")
    row.append(_line_no(new_no), style="dim")
    row.append("│   ", style="dim")
    row.append(body, style="white")
    return row


def _render_diff_body(diff: str) -> Group:
    lines = diff.splitlines()
    rows: list[Text] = []

    old_line = new_line = 0
    in_hunk = False

    for line in lines:
        if line.startswith("---") or line.startswith("+++"):
            rows.append(_render_diff_line(line, old_no=None, new_no=None))
            continue

        m = _HUNK_RE.match(line)
        if m:
            old_line = int(m.group(1))
            new_line = int(m.group(3))
            in_hunk = True
            rows.append(_render_hunk_header(line))
            continue

        if not in_hunk:
            continue

        sign = line[:1] if line else ""
        if sign == "-":
            rows.append(_render_diff_line(line, old_no=old_line, new_no=None))
            old_line += 1
        elif sign == "+":
            rows.append(_render_diff_line(line, old_no=None, new_no=new_line))
            new_line += 1
        elif sign == " ":
            rows.append(_render_diff_line(line, old_no=old_line, new_no=new_line))
            old_line += 1
            new_line += 1
        else:
            rows.append(_render_diff_line(line, old_no=None, new_no=None))

    if not rows:
        rows.append(Text("(no changes)", style="dim italic"))

    return Group(*rows)


def render_unified_diff(diff: str, *, path: str = "") -> Panel:
    """Return a Rich panel with a colored, line-numbered unified diff."""
    added, removed = _diff_stats(diff.splitlines())
    body = _render_diff_body(diff)
    return Panel(
        body,
        title=_format_title(path, added, removed),
        title_align="left",
        border_style="bright_blue",
        box=box.ROUNDED,
        padding=(0, 1),
        expand=False,
    )