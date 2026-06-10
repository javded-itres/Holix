"""Core+ slash commands for strict TUI (delegates to shared AgentCommands)."""

from cli.shared.commands.agent_commands import SLASH_COMMANDS, AgentCommands

SlashCommandsCore = AgentCommands

__all__ = ["SlashCommandsCore", "SLASH_COMMANDS"]