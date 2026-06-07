"""Fuzzy matching for slash-command autocomplete dropdowns."""

from __future__ import annotations

from cli.shared.commands.registry import SLASH_COMMANDS
from cli.shared.slash_input import normalize_slash_input

SlashCommandMatch = tuple[str, str]


def fuzzy_score(query: str, text: str) -> int:
    """Higher score = better match."""
    if not query:
        return 100
    query = query.lower()
    text_lower = text.lower()

    if query in text_lower:
        return 1000 - (text_lower.find(query) * 5)

    score = 0
    q_idx = 0
    for char in text_lower:
        if q_idx < len(query) and char == query[q_idx]:
            score += 10
            q_idx += 1
            if q_idx == len(query):
                break
    if q_idx == len(query):
        score += 50
    return score


def slash_line_query(line: str) -> str | None:
    """Return text after '/' when the line is a slash command prefix, else None."""
    normalized = normalize_slash_input(line)
    stripped = normalized.strip()
    if not stripped.startswith("/"):
        return None
    return stripped[1:].strip()


def match_slash_commands(
    line: str,
    commands: list[SlashCommandMatch] | None = None,
    *,
    limit: int = 8,
) -> list[SlashCommandMatch]:
    """Rank slash commands for the current input line."""
    query = slash_line_query(line)
    if query is None:
        return []

    pool = commands if commands is not None else SLASH_COMMANDS
    scored: list[tuple[int, str, str]] = []
    for cmd, desc in pool:
        cmd_clean = cmd[1:]
        score = fuzzy_score(query, cmd_clean)
        if query and cmd_clean.lower().startswith(query.lower()):
            score += 3000 - len(cmd_clean)
        if score > 0:
            scored.append((score, cmd, desc))

    scored.sort(reverse=True)
    return [(cmd, desc) for _, cmd, desc in scored[:limit]]