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