"""Custom sub-agent type storage and profile bindings."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.external_cli.assignment import assign_cli_to_subagent
from core.external_cli.store import ExternalCliStore
from core.subagents.registry import get_subagent_config, list_available_subagents
from core.subagents.spawn import prepare_subagent_config
from core.subagents.store import (
    CustomSubAgentType,
    SubAgentTypeStore,
    cleanup_custom_type_profile_bindings,
    sync_custom_type_profile_bindings,
    validate_custom_type_name,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


def test_validate_custom_type_name_rejects_builtin() -> None:
    with pytest.raises(ValueError, match="reserved"):
        validate_custom_type_name("coder")


def test_store_upsert_and_registry_lookup(holix_home) -> None:
    store = SubAgentTypeStore("default")
    custom = CustomSubAgentType(
        name="security-auditor",
        description="Security review specialist",
        system_prompt="You audit code for security issues.",
        tools=["read_file", "list_directory"],
        skills=["git"],
        mcp_servers=["filesystem"],
        model_slot="main",
    )
    store.upsert(custom)

    cfg = get_subagent_config("security-auditor", profile="default")
    assert cfg.system_prompt.startswith("You audit")
    assert "security-auditor" in {
        item["name"] for item in list_available_subagents(profile="default")
    }


def test_sync_profile_bindings(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:

    from cli.core import ProfileManager

    manager = ProfileManager()
    config = manager.load_profile("default")
    config.mcp_servers = {"filesystem": {"transport": "stdio", "command": "npx"}}
    manager.save_profile("default", config)

    custom = CustomSubAgentType(
        name="doc-writer",
        description="Docs",
        system_prompt="Write documentation.",
        skills=["writing"],
        mcp_servers=["filesystem"],
        external_cli_id="claude",
    )
    SubAgentTypeStore("default").upsert(custom)
    sync_custom_type_profile_bindings("default", custom)

    saved = manager.load_profile("default")
    assert saved.skill_assignments.get("doc-writer") == ["writing"]
    assert saved.mcp_assignments.get("doc-writer") == ["filesystem"]
    binding = ExternalCliStore("default").get_binding("claude")
    assert binding is not None
    assert binding.agent_slot == "doc-writer"

    cleanup_custom_type_profile_bindings("default", "doc-writer")
    saved2 = manager.load_profile("default")
    assert "doc-writer" not in (saved2.skill_assignments or {})
    assert "doc-writer" not in (saved2.mcp_assignments or {})


def test_prepare_subagent_custom_mcp_and_cli(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        "core.external_cli.platform.launch_supported",
        lambda: True,
    )
    custom = CustomSubAgentType(
        name="ops-runner",
        description="Ops",
        system_prompt="Run operational tasks.",
        mcp_servers=["filesystem"],
        external_cli_id="opencode",
    )
    SubAgentTypeStore("default").upsert(custom)
    sync_custom_type_profile_bindings("default", custom)
    assign_cli_to_subagent("default", "opencode", "ops-runner")

    parent = SimpleNamespace(
        subagent_default_process_mode="async",
        subagent_process_timeout=None,
        profile_name="default",
        mcp_assignments={"ops-runner": ["filesystem"]},
    )
    cfg = prepare_subagent_config("ops-runner", parent, instance_name="ops-runner")
    assert "filesystem" in cfg.mcp_servers
    assert "external_cli" in cfg.tools

def test_prepare_subagent_applies_provider_model_slot(
    holix_home, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Studio model_slot prov:provider:model must not fall back to default model."""
    from types import SimpleNamespace

    from core.subagents.spawn import resolve_subagent_model_id

    custom = CustomSubAgentType(
        name="kimi-worker",
        description="Uses kimi",
        system_prompt="You code carefully with tests.",
        model_slot="prov:litellm:kimi-k2.7-code",
    )
    SubAgentTypeStore("default").upsert(custom)

    parent = SimpleNamespace(
        subagent_default_process_mode="async",
        subagent_process_timeout=None,
        profile_name="default",
        mcp_assignments={},
        agent_models={},  # empty — old bug used get_agent_model_config → default
        providers={
            "litellm": {
                "base_url": "https://llm.example/v1",
                "api_key": "sk-test",
                "default_model": "smart",
                "available_models": [
                    "smart",
                    "kimi-k2.7-code",
                    "deepseek-v4-pro",
                ],
            }
        },
        default_provider="litellm",
        model="smart",
        base_url="https://llm.example/v1",
        api_key="sk-test",
        temperature=0.7,
    )

    # Direct resolver must return kimi, not smart
    assert (
        resolve_subagent_model_id(parent, "default", "prov:litellm:kimi-k2.7-code")
        == "kimi-k2.7-code"
    )
    assert resolve_subagent_model_id(parent, "default", "main") is None
    assert resolve_subagent_model_id(parent, "default", "") is None

    cfg = prepare_subagent_config("kimi-worker", parent, instance_name="kimi-worker")
    assert cfg.model == "kimi-k2.7-code"

    # With empty model_slot — inherit (no model override)
    custom2 = CustomSubAgentType(
        name="inherit-worker",
        description="Inherit",
        system_prompt="You help with general tasks carefully.",
        model_slot="",
    )
    SubAgentTypeStore("default").upsert(custom2)
    cfg2 = prepare_subagent_config(
        "inherit-worker", parent, instance_name="inherit-worker"
    )
    assert not cfg2.model
