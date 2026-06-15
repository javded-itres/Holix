"""External CLI sub-agent assignment."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.external_cli.assignment import (
    assign_cli_to_subagent,
    list_cli_assignment_rows,
    unassign_cli_subagent,
)
from core.external_cli.store import ExternalCliStore
from core.subagents.spawn import prepare_subagent_config


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


def test_assign_and_unassign_cli_subagent(holix_home) -> None:
    binding = assign_cli_to_subagent("default", "claude", "coder")
    assert binding.agent_slot == "coder"
    assert binding.enabled is True

    loaded = ExternalCliStore("default").get_binding("claude")
    assert loaded is not None
    assert loaded.agent_slot == "coder"

    unassign_cli_subagent("default", "claude")
    cleared = ExternalCliStore("default").get_binding("claude")
    assert cleared is not None
    assert cleared.agent_slot == ""


def test_assign_rejects_unknown_subagent(holix_home) -> None:
    with pytest.raises(ValueError, match="Unknown sub-agent"):
        assign_cli_to_subagent("default", "claude", "unknown-type")


def test_prepare_subagent_injects_external_cli_after_assign(
    holix_home, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.external_cli.platform.launch_supported",
        lambda: True,
    )
    from types import SimpleNamespace

    assign_cli_to_subagent("default", "opencode", "coder")
    parent = SimpleNamespace(
        subagent_default_process_mode="async",
        subagent_process_timeout=None,
        profile_name="default",
    )
    cfg = prepare_subagent_config("coder", parent, instance_name="coder")
    assert "external_cli" in cfg.tools

    unassign_cli_subagent("default", "opencode")
    cfg2 = prepare_subagent_config("coder", parent, instance_name="coder-2")
    assert "external_cli" not in cfg2.tools


def test_list_cli_assignment_rows(holix_home) -> None:
    assign_cli_to_subagent("default", "aider", "writer")
    rows = list_cli_assignment_rows("default", resolve_binary=lambda _spec: None)
    aider = next(r for r in rows if r.cli_id == "aider")
    assert aider.assigned is True
    assert aider.agent_slot == "writer"


@pytest.mark.asyncio
async def test_slash_launch_list(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.shared.commands.launch_commands import run_launch_command

    assign_cli_to_subagent("default", "claude", "coder")
    monkeypatch.setattr(
        "cli.shared.commands.launch_commands.launch_supported",
        lambda: True,
    )

    class Host:
        profile = "default"
        lines: list[str] = []

        def transcript_write(self, text: str) -> None:
            self.lines.append(text)

    host = Host()
    await run_launch_command(host, "/launch list")
    joined = "\n".join(host.lines)
    assert "claude" in joined
    assert "coder" in joined