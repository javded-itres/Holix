"""Shared CLI utilities (commands, host protocol)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["AgentHost", "AgentCommands", "SLASH_COMMANDS"]


def __getattr__(name: str) -> Any:
    if name == "AgentHost":
        from cli.shared.agent_host import AgentHost

        return AgentHost
    if name in ("AgentCommands", "SLASH_COMMANDS"):
        from cli.shared.commands.agent_commands import SLASH_COMMANDS, AgentCommands

        return {"AgentCommands": AgentCommands, "SLASH_COMMANDS": SLASH_COMMANDS}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    from cli.shared.agent_host import AgentHost
    from cli.shared.commands.agent_commands import SLASH_COMMANDS, AgentCommands
