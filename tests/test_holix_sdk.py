"""holix-sdk public API surface (protocols work without Holix runtime)."""

from __future__ import annotations

import holix_sdk
from holix_sdk.agent import AgentExtensionBase, SlashCommandSpec


def test_api_version() -> None:
    assert holix_sdk.__api_version__ == 1


def test_extension_exports() -> None:
    assert holix_sdk.HolixExtension is not None
    assert holix_sdk.ExtensionBase is not None
    assert holix_sdk.CAPABILITY_CLI == "cli"


def test_agent_module_exports() -> None:
    assert AgentExtensionBase is not None
    assert SlashCommandSpec is not None


def test_extension_base_defaults() -> None:
    class Ext(holix_sdk.ExtensionBase):
        name = "test"

    ext = Ext()
    assert ext.version == "0.0.0"
    assert ext.capabilities == frozenset()