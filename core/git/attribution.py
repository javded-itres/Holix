"""Mark commits the agent creates so GitHub can list Holix as a co-author.

Same mechanism as Claude Code: a ``Co-Authored-By`` trailer. GitHub links it
to a profile only when the email belongs to that GitHub account.
"""

from __future__ import annotations

import shlex

AGENT_NAME = "Holix agent"
AGENT_EMAIL = "noreply@holix-agent.ru"
COMMIT_TRAILER = f"Co-Authored-By: {AGENT_NAME} <{AGENT_EMAIL}>"


def attribute_agent_commit(command: str) -> str:
    """Append the Holix trailer to each ``git commit -m`` clause in *command*."""
    if not command or COMMIT_TRAILER in command:
        return command
    clauses = _shell_clauses(command)
    changed = False
    pieces: list[str] = []
    for clause, separator in clauses:
        updated = _attribute_clause(clause)
        if updated != clause:
            changed = True
        pieces.append(updated + separator)
    if not changed:
        return command
    return "".join(pieces)


def format_git_attribution_block() -> str:
    """Always-on reminder so a hand-written message keeps the same trailer."""
    return (
        "## Git attribution\n"
        "When you create a git commit, end the message with a blank line and "
        f"`{COMMIT_TRAILER}`. "
        "Leave the human as the author. Do not add this line to commits you did not create."
    )


def _attribute_clause(clause: str) -> str:
    stripped = clause.strip()
    if not stripped or COMMIT_TRAILER in clause:
        return clause
    try:
        tokens = shlex.split(stripped, posix=True)
    except ValueError:
        return clause
    if not _is_git_commit(tokens) or not _has_message_flag(tokens):
        return clause
    return clause.rstrip() + " -m " + shlex.quote(COMMIT_TRAILER)


def _is_git_commit(tokens: list[str]) -> bool:
    index = 0
    while index < len(tokens) and _is_env_assignment(tokens[index]):
        index += 1
    if index >= len(tokens):
        return False
    command = tokens[index].rsplit("/", 1)[-1]
    if command != "git":
        return False
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token == "commit":
            return True
        if token in {"-C", "-c", "--git-dir", "--work-tree"}:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return False
    return False


def _has_message_flag(tokens: list[str]) -> bool:
    for token in tokens:
        if token in {"-m", "--message"} or token.startswith("--message=") or token.startswith("-m"):
            if token not in {"-main", "-merge"} and not token.startswith("-m-"):
                return True
    return False


def _is_env_assignment(token: str) -> bool:
    return "=" in token and not token.startswith("-")


def _shell_clauses(command: str) -> list[tuple[str, str]]:
    """Split on ``&&``, ``||``, ``;``, and newlines without breaking quotes."""
    clauses: list[tuple[str, str]] = []
    start = 0
    quote: str | None = None
    escape = False
    index = 0
    length = len(command)
    while index < length:
        char = command[index]
        if escape:
            escape = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escape = True
            index += 1
            continue
        if quote:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        separator = ""
        if command.startswith("&&", index) or command.startswith("||", index):
            separator = command[index : index + 2]
        elif char in {";", "\n"}:
            separator = char
        if separator:
            clauses.append((command[start:index], separator))
            index += len(separator)
            start = index
            continue
        index += 1
    clauses.append((command[start:], ""))
    return clauses
