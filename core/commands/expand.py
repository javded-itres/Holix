"""Resolve a slash line against the custom-command registry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.commands.loader import CommandLoader
from core.commands.models import CommandInvocation
from core.commands.parse import expand_arguments
from core.commands.paths import project_commands_dir, user_commands_dir
from core.commands.reserved import RESERVED_SLASH_NAMES

_SLASH_NAME_RE = re.compile(
    r"^/([a-zA-Z0-9][a-zA-Z0-9_-]*(?::[a-zA-Z0-9][a-zA-Z0-9_-]*)*)(?:\s+(.*))?$",
    re.DOTALL,
)

_loader_cache: dict[tuple[str, str], CommandLoader] = {}


def builtin_slash_names() -> set[str]:
    """First-token names of built-in Holix slash commands (without ``/``)."""
    return set(RESERVED_SLASH_NAMES)


def parse_slash_line(text: str) -> tuple[str, str] | None:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return None
    match = _SLASH_NAME_RE.match(stripped)
    if not match:
        return None
    return match.group(1).lower(), (match.group(2) or "")


def get_command_loader(
    *, cwd: str | Path | None = None, agent: Any = None, host: Any = None
) -> CommandLoader:
    project = project_commands_dir(cwd=cwd, agent=agent, host=host)
    user = user_commands_dir()
    key = (str(project), str(user))
    loader = _loader_cache.get(key)
    if loader is None:
        loader = CommandLoader(project_dir=project, user_dir=user)
        _loader_cache[key] = loader
    return loader


def reload_command_loader(
    *, cwd: str | Path | None = None, agent: Any = None, host: Any = None
) -> CommandLoader:
    loader = get_command_loader(cwd=cwd, agent=agent, host=host)
    loader.reload()
    return loader


def resolve_custom_slash(
    text: str,
    *,
    cwd: str | Path | None = None,
    agent: Any = None,
    host: Any = None,
    allow_reserved: bool = False,
) -> CommandInvocation | None:
    parsed = parse_slash_line(text)
    if parsed is None:
        return None
    name, args = parsed
    if not allow_reserved and name in builtin_slash_names():
        return None
    loader = get_command_loader(cwd=cwd, agent=agent, host=host)
    command = loader.get(name)
    if command is None:
        return None
    prompt = expand_arguments(command.body, args)
    if not prompt.strip():
        return None
    return CommandInvocation(
        name=command.name,
        source=command.source,
        prompt=prompt,
        allowed_tools=command.allowed_tools,
        model=command.model,
        argument_hint=command.argument_hint,
        description=command.description,
    )
