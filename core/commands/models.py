"""Custom slash-command domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CustomCommand:
    """One markdown command file (``review.md`` → ``/review``)."""

    name: str
    path: Path
    source: str  # "project" | "user"
    description: str = ""
    argument_hint: str = ""
    allowed_tools: tuple[str, ...] = ()
    model: str | None = None
    body: str = ""


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    """Expanded prompt ready to send to the agent."""

    name: str
    source: str
    prompt: str
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    model: str | None = None
    argument_hint: str = ""
    description: str = ""
