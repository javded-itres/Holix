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
    # 1.2 is main but blocked until 1.1 completes (inferred sequential deps)
    assert len(result["main_tasks"]) == 0
    assert any(b.get("id") == "1.2" for b in result.get("blocked") or [])
    assert load_task_jobs(store, "feat-x").get("1.1") == result["spawned"][0]["job_id"]

    parent.subagents.spawn_typed.assert_awaited()
    call_args = parent.subagents.spawn_typed.await_args
    assert call_args.args[0] == "coder"
    # Subagent prompt includes graph context
    task_text = call_args.args[1]
    assert "depends_on" in task_text or "Task graph" in task_text


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
    # All tasks on main in self mode, ordered by graph (both in plan)
    assert len(result["plan"]) == 2
    assert result.get("graph_summary")
    parent.subagents.spawn_typed.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_respects_depends_on_waves(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store, "wave-x")
    store.write_artifact(
        "wave-x",
        "tasks",
        """# Tasks

- [ ] 1.1 Schema
  - **assignee:** `coder`
  - **reason:** schema

- [ ] 1.2 API (after schema)
  - **assignee:** `coder`
  - **reason:** api
  - **depends_on:** `1.1`

- [ ] 2.1 UI (parallel track, no dep)
  - **assignee:** `coder`
  - **reason:** ui
""",
    )
    store.set_apply_mode("wave-x", "subagents")

    handles = []

    async def _spawn(agent_type, task, **kwargs):
        h = MagicMock()
        h.name = f"{agent_type}-{len(handles)+1}"
        h.config.process_mode.value = "async"
        handles.append(h)
        return (h, None)

    parent = MagicMock()
    parent.config = MagicMock()
    parent.subagents = MagicMock()
    parent.subagents.spawn_typed = AsyncMock(side_effect=_spawn)

    from unittest.mock import patch

    with patch("core.config_utils.is_subagents_enabled", return_value=True):
        result = await dispatch_change_tasks(store, "wave-x", parent_agent=parent)

    assert result.get("ok") is True, result
    # Wave 1: 1.1 and 2.1 ready; 1.2 blocked by explicit depends_on
    spawned_ids = {j["task_id"] for j in result["spawned"]}
    assert "1.1" in spawned_ids
    assert "2.1" in spawned_ids
    assert "1.2" not in spawned_ids
    assert any(b.get("id") == "1.2" for b in result.get("blocked") or [])
    assert result.get("graph")
    assert len(result["graph"]["waves"]) >= 2
