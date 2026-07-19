"""Agent extension registry, self-ext policy, and hot-reload."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.extensions.agent_base import AgentExtensionBase, SlashCommandSpec
from core.extensions.agent_registry import (
    ENTRYPOINT_GROUP,
    agent_slash_commands,
    clear_agent_extension_cache,
    discover_agent_extensions,
    register_agent_extensions,
    reload_agent_extensions,
)
from core.extensions.self_ext_policy import (
    agent_allows_self_extensions,
    is_messenger_multi_user_runtime,
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

        def unregister(self, name: str) -> bool:
            if name in self.tools:
                del self.tools[name]
                return True
            return False

        def get_tool_names(self) -> list[str]:
            return list(self.tools.keys())

    class FakeAgent:
        def __init__(self) -> None:
            self.tools = FakeRegistry()
            self.config = type("Cfg", (), {"profile_name": "default", "data_dir": "."})()
            self.client = None

    class LocalExt(AgentExtensionBase):
        name = "local-test"
        version = "0.0.1"
        permissions = frozenset({"tools"})

        def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
            commands.append(SlashCommandSpec("/local-test", "test"))

        def register_tools(self, registry, agent) -> None:
            class T:
                name = "local_test_tool"

            registry.register(T())

    with patch(
        "core.extensions.agent_registry.discover_agent_extensions",
        return_value=(LocalExt(),),
    ):
        clear_agent_extension_cache()
        agent = FakeAgent()
        register_agent_extensions(agent)
        cmds = agent_slash_commands()
        assert any(c.command == "/local-test" for c in cmds)
        assert "local_test_tool" in agent.tools.tools
        assert "local_test_tool" in getattr(agent, "_extension_tool_names", set())
    clear_agent_extension_cache()


def test_reload_agent_extensions_unregisters_old_tools() -> None:
    clear_agent_extension_cache()

    class FakeRegistry:
        def __init__(self) -> None:
            self.tools: dict[str, object] = {}

        def register(self, tool: object) -> None:
            self.tools[getattr(tool, "name", str(tool))] = tool

        def unregister(self, name: str) -> bool:
            if name in self.tools:
                del self.tools[name]
                return True
            return False

        def get_tool_names(self) -> list[str]:
            return list(self.tools.keys())

    class FakeAgent:
        def __init__(self) -> None:
            self.tools = FakeRegistry()
            self.config = type("Cfg", (), {"profile_name": "default", "data_dir": "."})()
            self.client = None

    class ExtA(AgentExtensionBase):
        name = "ext-a"
        version = "0.0.1"
        permissions = frozenset({"tools"})

        def register_tools(self, registry, agent) -> None:
            class T:
                name = "tool_a"

            registry.register(T())

    class ExtB(AgentExtensionBase):
        name = "ext-b"
        version = "0.0.1"
        permissions = frozenset({"tools"})

        def register_tools(self, registry, agent) -> None:
            class T:
                name = "tool_b"

            registry.register(T())

    agent = FakeAgent()
    with patch(
        "core.extensions.agent_registry.discover_agent_extensions",
        return_value=(ExtA(),),
    ):
        register_agent_extensions(agent)
    assert "tool_a" in agent.tools.tools

    with patch(
        "core.extensions.agent_registry.discover_agent_extensions",
        return_value=(ExtB(),),
    ):
        result = reload_agent_extensions(agent)
    assert result["ok"] is True
    assert "tool_a" not in agent.tools.tools
    assert "tool_b" in agent.tools.tools
    assert "ext-b" in result["loaded"]
    clear_agent_extension_cache()


def test_messenger_env_denies_self_extensions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_SELF_EXTENSIONS", raising=False)
    monkeypatch.setenv("HOLIX_MESSENGER_HOST", "telegram")
    assert is_messenger_multi_user_runtime() is True
    assert agent_allows_self_extensions() is False


def test_self_extensions_env_override_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_MESSENGER_HOST", "max")
    monkeypatch.setenv("HOLIX_SELF_EXTENSIONS", "1")
    assert agent_allows_self_extensions() is True


def test_self_extensions_env_override_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_MESSENGER_HOST", raising=False)
    monkeypatch.setenv("HOLIX_SELF_EXTENSIONS", "0")
    assert agent_allows_self_extensions() is False


def test_config_flag_false_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_SELF_EXTENSIONS", raising=False)
    monkeypatch.delenv("HOLIX_MESSENGER_HOST", raising=False)

    class Agent:
        config = type("C", (), {"self_extensions_enabled": False})()

    assert agent_allows_self_extensions(Agent()) is False


@pytest.mark.asyncio
async def test_manage_create_denied_on_messenger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_MESSENGER_HOST", "telegram")
    monkeypatch.delenv("HOLIX_SELF_EXTENSIONS", raising=False)

    from core.tools.agent_extensions import ManageAgentExtensionsTool

    class Agent:
        config = type("C", (), {"profile_name": "default", "self_extensions_enabled": False})()

    tool = ManageAgentExtensionsTool(Agent())
    raw = await tool.execute(action="create", name="x", description="y")
    data = json.loads(raw)
    assert data["ok"] is False
    assert data["error"] == "self_extensions_denied"


@pytest.mark.asyncio
async def test_manage_create_hot_reloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOLIX_MESSENGER_HOST", raising=False)
    monkeypatch.setenv("HOLIX_SELF_EXTENSIONS", "1")

    from core.tools.agent_extensions import ManageAgentExtensionsTool

    class FakeRegistry:
        def __init__(self) -> None:
            self.tools: dict[str, object] = {}

        def register(self, tool: object) -> None:
            self.tools[getattr(tool, "name", str(tool))] = tool

        def unregister(self, name: str) -> bool:
            if name in self.tools:
                del self.tools[name]
                return True
            return False

        def get_tool_names(self) -> list[str]:
            return list(self.tools.keys())

    reloads: list[dict] = []

    class Agent:
        def __init__(self) -> None:
            self.tools = FakeRegistry()
            self.config = type(
                "C",
                (),
                {
                    "profile_name": "test-hot-reload",
                    "self_extensions_enabled": True,
                    "data_dir": str(tmp_path),
                },
            )()
            self.client = None

        def reload_agent_extensions(self) -> dict:
            result = {"ok": True, "loaded": ["notes_hot"], "removed_tools": []}
            reloads.append(result)
            return result

    # Point profile extensions under tmp
    def _fake_profile_dir(name: str) -> Path:
        d = tmp_path / "profiles" / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(
        "core.profile.names.profile_dir_for_name",
        _fake_profile_dir,
    )
    # control/scaffold use profile_agent_extensions_dir via control
    from core.extensions import control as control_mod

    monkeypatch.setattr(
        control_mod,
        "profile_agent_extensions_dir",
        lambda profile: _fake_profile_dir(profile) / "extensions",
    )

    tool = ManageAgentExtensionsTool(Agent())
    raw = await tool.execute(
        action="create", name="notes_hot", description="Hot reload test"
    )
    data = json.loads(raw)
    assert data["ok"] is True
    assert data.get("hot_reload", {}).get("ok") is True
    assert reloads, "expected agent.reload_agent_extensions to be called"
    agent_py = Path(data["agent_py"])
    assert agent_py.is_file()
