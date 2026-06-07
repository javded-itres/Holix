"""Slash-command input normalization (shared by TUI, Telegram, CLI)."""

from __future__ import annotations

import re
import sys

# macOS RU layout: US "/" key may type "," or "." — Shift+7 still gives "/"
MACOS_SLASH_ALIASES: frozenset[str] = frozenset({",", ".", "?", "\\"})
_SLASH_CMD_RE = re.compile(r"^[.,?\\]([a-zA-Z0-9_-]|$)")


def is_macos() -> bool:
    return sys.platform == "darwin"


def normalize_slash_input(text: str) -> str:
    """Map macOS RU layout slash aliases to '/' for slash commands."""
    if not text or not is_macos():
        return text
    leading = len(text) - len(text.lstrip())
    body = text[leading:]
    if not body or body[0] == "/":
        return text
    if body[0] in MACOS_SLASH_ALIASES and _SLASH_CMD_RE.match(body):
        return text[:leading] + "/" + body[1:]
    return text


def is_slash_command(text: str) -> bool:
    """True if text is (or normalizes to) a slash command."""
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith("/"):
        return True
    if is_macos():
        return normalize_slash_input(stripped).startswith("/")
    return False


def slash_command_prefix(line: str) -> str | None:
    """Return normalized slash command token for completion (/help), or None."""
    stripped = line.strip()
    if not stripped:
        return None
    normalized = normalize_slash_input(stripped)
    if not normalized.startswith("/"):
        return None
    return normalized.split()[0]


def slash_command_token(text: str) -> str:
    """Normalized command name only: ``/models@Bot`` → ``/models``."""
    stripped = text.strip()
    if not stripped:
        return ""
    normalized = normalize_slash_input(stripped).lower()
    if not normalized.startswith("/"):
        return ""
    token = normalized.split(maxsplit=1)[0]
    if "@" in token:
        token = token.split("@", 1)[0]
    return token


def is_mode_slash(text: str) -> bool:
    """True for ``/mode`` or ``/mode hybrid`` — not ``/models`` or ``/model``."""
    return slash_command_token(text) == "/mode"


def is_models_slash(text: str) -> bool:
    """True for ``/models`` or ``/model`` (LLM picker), not execution mode."""
    return slash_command_token(text) in ("/models", "/model")