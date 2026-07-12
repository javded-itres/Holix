"""Agent extension registry."""

from __future__ import annotations

from core.extensions.agent_base import AgentExtensionBase, SlashCommandSpec
from core.extensions.agent_registry import (
    ENTRYPOINT_GROUP,
    agent_slash_commands,
    clear_agent_extension_cache,
    discover_agent_extensions,
    register_agent_extensions,
)


def test_agent_entrypoint_group_name() -> None:
    assert ENTRYPOINT_GROUP == "holix.agent.extensions"


def test_demo_agent_extension_when_installed() -> None:
    clear_agent_extension_cache()
    exts = discover_agent_extensions()
    names = {e.name for e in exts}
    if "demo" not in names:
        return
    demo = next(e for e in exts if e.name == "demo")
    assert demo.version == "0.1.0"


def test_register_agent_extensions_adds_slash_commands() -> None:
    clear_agent_extension_cache()

    class FakeRegistry:
        def __init__(self) -> None:
            self.tools: dict[str, object] = {}

        def register(self, tool: object) -> None:
            self.tools[getattr(tool, "name", str(tool))] = tool

    class FakeAgent:
        def __init__(self) -> None:
            self.tools = FakeRegistry()
            self.config = type("Cfg", (), {"profile_name": "default"})()

    class LocalExt(AgentExtensionBase):
        name = "local-test"
        version = "0.0.1"
        permissions = frozenset({"tools"})

        def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
            commands.append(SlashCommandSpec("/local-test", "test"))

    from unittest.mock import patch

    with patch(
        "core.extensions.agent_registry.discover_agent_extensions",
        return_value=(LocalExt(),),
    ):
        clear_agent_extension_cache()
        register_agent_extensions(FakeAgent())
        cmds = agent_slash_commands()
        assert any(c.command == "/local-test" for c in cmds)
    clear_agent_extension_cache()