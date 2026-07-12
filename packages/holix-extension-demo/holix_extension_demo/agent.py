"""Agent extension entry point."""

from __future__ import annotations

from typing import Any

from holix_sdk.agent import AgentExtensionBase, SlashCommandSpec

from holix_extension_demo.tool import DemoEchoTool


class DemoAgentExtension(AgentExtensionBase):
    name = "demo"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    permissions = frozenset({"tools"})

    def register_tools(self, registry: Any, agent: Any) -> None:
        registry.register(DemoEchoTool())

    def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
        commands.append(SlashCommandSpec(command="/demo", description="Holix extension demo command"))

    def augment_system_prompt(self, profile: str) -> str | None:
        return "## Extension demo\nThe `demo_echo` tool is available from holix-extension-demo."


def get_agent_extension() -> DemoAgentExtension:
    return DemoAgentExtension()