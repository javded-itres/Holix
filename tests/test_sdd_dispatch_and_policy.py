"""SDD dispatch mapping, soft gate, task jobs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.sdd.dispatch import dispatch_change_tasks, load_task_jobs
from core.sdd.policy import soft_gate_warning
from core.sdd.store import SpecStore


def _ready_change(store: SpecStore, change_id: str = "feat-x") -> None:
    store.init(example_domain="app")
    store.create_change(change_id, domain="app")
    store.write_artifact(
        change_id,
        "proposal",
        "# Proposal\n\n## Why\nNeed feature X for users.\n\n## What\nAdd X.\n\n## Impact\nApp module.\n",
    )
    store.write_artifact(
        change_id,
        "specs",
        "## ADDED Requirements\n\n### Requirement: Feature X\nThe system SHALL support X.\n\n#### Scenario: OK\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n",
        domain="app",
    )
    store.write_artifact(
        change_id,
        "tasks",
        """# Tasks

- [ ] 1.1 Backend work
  - **assignee:** `coder`
  - **reason:** api

- [ ] 1.2 Shared config
  - **assignee:** `main`
  - **reason:** shared
""",
    )


def test_soft_gate_warns_without_mode(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    warn = soft_gate_warning(tmp_path, writing_path="src/app.py")
    assert warn is not None
    assert "apply-ready" in warn or "execution mode" in warn

    # openspec writes are ignored
    assert soft_gate_warning(tmp_path, writing_path="openspec/changes/feat-x/tasks.md") is None

    store.set_apply_mode("feat-x", "self")
    assert soft_gate_warning(tmp_path, writing_path="src/app.py") is None


@pytest.mark.asyncio
async def test_dispatch_spawns_non_main(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    store.set_apply_mode("feat-x", "subagents")

    handle = MagicMock()
    handle.name = "coder-1"
    handle.config.process_mode.value = "async"

    parent = MagicMock()
    parent.config = MagicMock()
    parent.subagents = MagicMock()
    parent.subagents.spawn_typed = AsyncMock(return_value=(handle, None))

    # is_subagents_enabled may inspect config — patch

    result = await dispatch_change_tasks(store, "feat-x", parent_agent=parent)
    # may fail if subagents disabled — force via mock path
    if not result.get("ok") and "disabled" in str(result.get("error", "")):
        # enable by patching
        from unittest.mock import patch

        with patch("core.config_utils.is_subagents_enabled", return_value=True):
            result = await dispatch_change_tasks(store, "feat-x", parent_agent=parent)

    assert result["ok"] is True
    assert len(result["spawned"]) == 1
    # Single non-main task → bare type name (or resolved specialisation)
    assert result["spawned"][0]["executor"] == "coder"
    assert result["spawned"][0]["job_id"]
    assert len(result["main_tasks"]) == 1
    assert load_task_jobs(store, "feat-x").get("1.1") == result["spawned"][0]["job_id"]

    parent.subagents.spawn_typed.assert_awaited()
    call_args = parent.subagents.spawn_typed.await_args
    assert call_args.args[0] == "coder"


@pytest.mark.asyncio
async def test_dispatch_self_no_spawn(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    store.set_apply_mode("feat-x", "self")
    parent = MagicMock()
    parent.subagents = MagicMock()
    result = await dispatch_change_tasks(store, "feat-x", parent_agent=parent)
    assert result["ok"] is True
    assert result["spawned"] == []
    assert len(result["main_tasks"]) == 2
    parent.subagents.spawn_typed.assert_not_called()
