"""Format custom commands for /help and /commands."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from core.commands.expand import get_command_loader
from core.commands.models import CustomCommand


def list_custom_commands(
    *,
    cwd: str | Path | None = None,
    agent: Any = None,
    host: Any = None,
) -> list[CustomCommand]:
    return get_command_loader(cwd=cwd, agent=agent, host=host).list_commands()


def custom_slash_pairs(
    *,
    cwd: str | Path | None = None,
    agent: Any = None,
    host: Any = None,
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for command in list_custom_commands(cwd=cwd, agent=agent, host=host):
        hint = f" {command.argument_hint}" if command.argument_hint else ""
        desc = command.description or "Custom command"
        tag = "project" if command.source == "project" else "user"
        pairs.append((f"/{command.name}{hint}", f"{desc} ({tag})"))
    return pairs


def format_custom_commands_help(
    commands: Sequence[CustomCommand] | None = None,
    *,
    cwd: str | Path | None = None,
    agent: Any = None,
    host: Any = None,
) -> str:
    rows = (
        list(commands)
        if commands is not None
        else list_custom_commands(cwd=cwd, agent=agent, host=host)
    )
    if not rows:
        return ""
    lines = ["", "Custom commands:"]
    for command in rows:
        hint = f" {command.argument_hint}" if command.argument_hint else ""
        desc = command.description or "—"
        lines.append(f"  /{command.name}{hint}  — {desc}  [{command.source}]")
    lines.append("  /commands reload  — rescan .holix/commands and ~/.holix/commands")
    return "\n".join(lines)
