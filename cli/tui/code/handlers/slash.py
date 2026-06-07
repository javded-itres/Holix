"""Core+ slash commands for strict TUI (delegates to shared AgentCommands)."""

from cli.shared.commands.agent_commands import AgentCommands, SLASH_COMMANDS

SlashCommandsCore = AgentCommands

__all__ = ["SlashCommandsCore", "SLASH_COMMANDS"]