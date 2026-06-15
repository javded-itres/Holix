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


def is_skill_invoke_line(line: str) -> bool:
    """True when the line is `/skill` or `/skill …` (not `/skills`)."""
    normalized = normalize_slash_input(line).strip().lower()
    return normalized == "/skill" or normalized.startswith("/skill ")


def skill_invoke_name_query(line: str) -> str | None:
    """Skill-name fragment after `/skill` for autocomplete, or None."""
    if not is_skill_invoke_line(line):
        return None
    normalized = normalize_slash_input(line).strip()
    if normalized.lower() == "/skill":
        return ""
    rest = normalized[6:].strip()
    return rest.split(maxsplit=1)[0] if rest else ""


def match_slash_commands(
    line: str,
    commands: list[SlashCommandMatch] | None = None,
    *,
    limit: int = 8,
) -> list[SlashCommandMatch]:
    """Rank slash commands for the current input line."""
    if is_skill_invoke_line(line):
        return []

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


def match_skill_invoke_commands(
    line: str,
    commands: list[SlashCommandMatch],
    *,
    limit: int = 8,
) -> list[SlashCommandMatch]:
    """Rank `/skill <name>` entries for skill-name autocomplete."""
    query = skill_invoke_name_query(line)
    if query is None:
        return []

    prefix = "/skill "
    scored: list[tuple[int, str, str]] = []
    for cmd, desc in commands:
        if not cmd.lower().startswith(prefix):
            continue
        skill_name = cmd[len(prefix) :]
        score = fuzzy_score(query, skill_name)
        if query and skill_name.lower().startswith(query.lower()):
            score += 3000 - len(skill_name)
        if score > 0:
            scored.append((score, cmd, desc))

    scored.sort(reverse=True)
    return [(cmd, desc) for _, cmd, desc in scored[:limit]]