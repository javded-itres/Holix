"""Auto-complete SDD tasks when subagents finish."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.sdd.dispatch import dispatch_change_tasks, load_task_jobs
from core.sdd.store import SpecStore
from core.sdd.task_completion import (
    cancel_sdd_subagents_after_check,
    parse_sdd_task_marker,
    try_complete_sdd_task_for_subagent,
    write_task_job,
)
from core.sdd.tasks import parse_tasks_markdown
from core.subagents.base import (
    SubAgentConfig,
    SubAgentHandle,
    SubAgentResult,
    SubAgentStatus,
)
from core.subagents.manager import SubAgentManager


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


def test_handle_status_exposes_followed_process():
    handle = SubAgentHandle(
        name="python-coder",
        config=SubAgentConfig(name="python-coder"),
        status=SubAgentStatus.RUNNING,
        task_preview="[SDD change=feat-x task=1.1]",
    )
    handle.followed_process = True
    handle.studio_process_id = "proc-dev"
    handle.studio_worktree = "/tmp/.holix/worktrees/feat-x"
    handle.studio_sdd = {
        "change_id": "feat-x",
        "task_id": "1.1",
        "worktree": "/tmp/.holix/worktrees/feat-x",
    }
    row = handle.to_status_dict(include_activity=False, include_result=False)
    assert row["followed_process"] is True
    assert row["studio_process_id"] == "proc-dev"
    assert row["sdd"]["task_id"] == "1.1"
    assert row["worktree"] == "/tmp/.holix/worktrees/feat-x"


def test_parse_sdd_marker():
    m = parse_sdd_task_marker("[SDD change=feat-x task=1.1 project=user_catalog]\nDo stuff")
    assert m == {
        "change_id": "feat-x",
        "task_id": "1.1",
        "project": "user_catalog",
    }
    assert parse_sdd_task_marker("no marker") is None


def test_auto_complete_via_marker(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    write_task_job(tmp_path, "feat-x", "1.1", "coder-python")

    result = try_complete_sdd_task_for_subagent(
        job_id="coder-python",
        task_preview="[SDD change=feat-x task=1.1]\nBackend work",
        success=True,
        workspace=tmp_path,
    )
    assert result and result.get("ok") is True
    tasks = parse_tasks_markdown(
        (tmp_path / "openspec/changes/feat-x/tasks.md").read_text(encoding="utf-8")
    )
    by_id = {t.id: t for t in tasks}
    assert by_id["1.1"].done is True
    assert by_id["1.2"].done is False


def test_auto_complete_via_job_index(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    write_task_job(tmp_path, "feat-x", "1.1", "coder-1")

    result = try_complete_sdd_task_for_subagent(
        job_id="coder-1",
        task_preview="",  # no marker — use .task-jobs.json reverse map
        success=True,
        workspace=tmp_path,
    )
    assert result and result.get("ok") is True
    tasks = parse_tasks_markdown(
        (tmp_path / "openspec/changes/feat-x/tasks.md").read_text(encoding="utf-8")
    )
    assert any(t.id == "1.1" and t.done for t in tasks)


def test_skip_studio_process_step_auto_complete(tmp_path: Path):
    from core.sdd.task_completion import is_studio_process_step_job

    store = SpecStore(tmp_path)
    _ready_change(store)
    write_task_job(tmp_path, "feat-x", "1.1", "python-coder")
    assert is_studio_process_step_job(
        job_id="p-proc-102d1-python-coder-ab12",
        task_preview="",
    )
    result = try_complete_sdd_task_for_subagent(
        job_id="python-coder",
        task_preview="You are a step in a Studio process. Do the work.",
        success=True,
        workspace=tmp_path,
    )
    assert result is None
    tasks = parse_tasks_markdown(
        (tmp_path / "openspec/changes/feat-x/tasks.md").read_text(encoding="utf-8")
    )
    assert any(t.id == "1.1" and not t.done for t in tasks)


def test_no_auto_complete_on_failure(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    result = try_complete_sdd_task_for_subagent(
        job_id="coder",
        task_preview="[SDD change=feat-x task=1.1]\nx",
        success=False,
        workspace=tmp_path,
    )
    assert result is None
    tasks = parse_tasks_markdown(
        (tmp_path / "openspec/changes/feat-x/tasks.md").read_text(encoding="utf-8")
    )
    assert all(not t.done for t in tasks)


@pytest.mark.asyncio
async def test_dispatch_records_structured_jobs(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    store.set_apply_mode("feat-x", "subagents")

    handle = MagicMock()
    handle.name = "coder"
    handle.config.process_mode.value = "async"

    parent = MagicMock()
    parent.config = MagicMock()
    parent.config.workspace_root = str(tmp_path)
    parent.subagents = MagicMock()
    from unittest.mock import AsyncMock, patch

    parent.subagents.spawn_typed = AsyncMock(return_value=(handle, None))

    with patch("core.config_utils.is_subagents_enabled", return_value=True):
        result = await dispatch_change_tasks(store, "feat-x", parent_agent=parent)

    assert result["ok"]
    jobs = load_task_jobs(store, "feat-x")
    assert jobs.get("1.1") == "coder"
    # spawn task text includes SDD marker
    call_task = parent.subagents.spawn_typed.await_args.args[1]
    assert "[SDD change=feat-x task=1.1]" in call_task


@pytest.mark.asyncio
async def test_dispatch_followed_process_job_fields(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    store.set_apply_mode("feat-x", "subagents")

    handle = MagicMock()
    handle.name = "python-coder"
    handle.config.process_mode.value = "async"
    handle.followed_process = True
    handle.studio_process_id = "proc-dev"
    handle.studio_worktree = "/tmp/.holix/worktrees/feat-x"
    handle.studio_sdd = {
        "change_id": "feat-x",
        "task_id": "1.1",
        "project": "",
        "worktree": "/tmp/.holix/worktrees/feat-x",
    }

    parent = MagicMock()
    parent.config = MagicMock()
    parent.config.workspace_root = str(tmp_path)
    parent.subagents = MagicMock()
    from unittest.mock import patch

    parent.subagents.spawn_typed = AsyncMock(return_value=(handle, None))

    with patch("core.config_utils.is_subagents_enabled", return_value=True):
        result = await dispatch_change_tasks(store, "feat-x", parent_agent=parent)

    spawned = {j["task_id"]: j for j in result["spawned"]}
    job = spawned["1.1"]
    assert job["followed_process"] is True
    assert job["studio_process_id"] == "proc-dev"
    assert job["worktree"] == "/tmp/.holix/worktrees/feat-x"
    assert "wait_subagent_result" in job["wait_hint"]
    assert "followed_process" in result["message"]


@pytest.mark.asyncio
async def test_wait_subagent_exposes_worktree():
    import json

    from core.tools.subagents import WaitSubAgentResultTool

    handle = SubAgentHandle(
        name="python-coder",
        config=SubAgentConfig(name="python-coder"),
        status=SubAgentStatus.COMPLETED,
        result=SubAgentResult(name="python-coder", success=True, response="done"),
    )
    handle.followed_process = True
    handle.studio_process_id = "proc-dev"
    handle.studio_process_run_id = "run-abc"
    handle.studio_worktree = "/tmp/.holix/worktrees/feat-x"
    handle.studio_sdd = {
        "change_id": "feat-x",
        "task_id": "1.1",
        "worktree": "/tmp/.holix/worktrees/feat-x",
    }

    mgr = MagicMock()
    mgr.get_handle = MagicMock(return_value=handle)
    mgr.wait_for = AsyncMock(return_value=handle.result)
    parent = MagicMock()
    parent.subagents = mgr
    parent.config = MagicMock()
    parent.config.profile_name = "default"

    raw = await WaitSubAgentResultTool(parent).execute(job_id="python-coder")
    payload = json.loads(raw)
    assert payload["followed_process"] is True
    assert payload["worktree"] == "/tmp/.holix/worktrees/feat-x"
    assert payload["sdd"]["change_id"] == "feat-x"


def test_manager_finish_marks_sdd_task(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    write_task_job(tmp_path, "feat-x", "1.1", "coder")

    parent = MagicMock()
    parent.config = MagicMock()
    parent.config.workspace_root = str(tmp_path)
    parent.emit = MagicMock()

    mgr = SubAgentManager(parent)
    handle = SubAgentHandle(
        name="coder",
        config=SubAgentConfig(name="coder"),
        status=SubAgentStatus.COMPLETED,
        task_preview="[SDD change=feat-x task=1.1]\nBackend",
        result=SubAgentResult(name="coder", success=True, response="done", steps_taken=3),
    )
    mgr._handles["coder"] = handle
    mgr._emit_finished_once(handle)

    tasks = parse_tasks_markdown(
        (tmp_path / "openspec/changes/feat-x/tasks.md").read_text(encoding="utf-8")
    )
    assert any(t.id == "1.1" and t.done for t in tasks)


def test_manager_respawn_same_job_id_auto_checks_again(tmp_path: Path):
    """Reusing job name after a finished run must still mark SDD tasks."""
    store = SpecStore(tmp_path)
    _ready_change(store)
    write_task_job(tmp_path, "feat-x", "1.1", "coder")

    parent = MagicMock()
    parent.config = MagicMock()
    parent.config.workspace_root = str(tmp_path)
    parent.emit = MagicMock()

    mgr = SubAgentManager(parent)
    first = SubAgentHandle(
        name="coder",
        config=SubAgentConfig(name="coder"),
        status=SubAgentStatus.COMPLETED,
        task_preview="[SDD change=feat-x task=1.1]\nfirst",
        result=SubAgentResult(name="coder", success=True, response="ok"),
    )
    mgr._handles["coder"] = first
    mgr._emit_finished_once(first)
    assert "coder" in mgr._finished_emitted

    # Uncheck so we can observe a second auto-complete
    store.check_task("feat-x", task_id="1.1", done=False)

    second = SubAgentHandle(
        name="coder",
        config=SubAgentConfig(name="coder"),
        status=SubAgentStatus.RUNNING,
        task_preview="[SDD change=feat-x task=1.1]\nsecond",
    )
    mgr._register_handle("coder", second)
    assert "coder" not in mgr._finished_emitted

    second.status = SubAgentStatus.COMPLETED
    second.result = SubAgentResult(name="coder", success=True, response="ok2")
    mgr.notify_handle_finished("coder")

    tasks = parse_tasks_markdown(
        (tmp_path / "openspec/changes/feat-x/tasks.md").read_text(encoding="utf-8")
    )
    assert any(t.id == "1.1" and t.done for t in tasks)


@pytest.mark.asyncio
async def test_check_task_cancels_running_subagent(tmp_path: Path):
    """Marking a task done must stop the still-running SDD subagent for that task."""
    store = SpecStore(tmp_path)
    _ready_change(store)
    write_task_job(tmp_path, "feat-x", "1.1", "coder")

    parent = MagicMock()
    parent.config = MagicMock()
    parent.config.workspace_root = str(tmp_path)

    running = SubAgentHandle(
        name="coder",
        config=SubAgentConfig(name="coder"),
        status=SubAgentStatus.RUNNING,
        task_preview="[SDD change=feat-x task=1.1]\nBackend work",
    )
    mgr = MagicMock()
    mgr.list_active = MagicMock(return_value=[running])
    mgr.terminate = AsyncMock(return_value=True)
    parent.subagents = mgr

    result = store.check_task("feat-x", task_id="1.1", done=True)
    cancel = await cancel_sdd_subagents_after_check(
        parent,
        project_root=tmp_path,
        change_id="feat-x",
        task_id="1.1",
        done=True,
        tasks_done=result["tasks_done"],
        tasks_total=result["tasks_total"],
    )
    assert "coder" in cancel["cancelled_jobs"]
    mgr.terminate.assert_awaited_with("coder")


@pytest.mark.asyncio
async def test_all_tasks_done_cancels_remaining_sdd_jobs(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    write_task_job(tmp_path, "feat-x", "1.1", "coder-1")
    write_task_job(tmp_path, "feat-x", "1.2", "coder-2")

    store.check_task("feat-x", task_id="1.1", done=True)
    result = store.check_task("feat-x", task_id="1.2", done=True)
    assert result["tasks_done"] == result["tasks_total"] == 2

    parent = MagicMock()
    orphan = SubAgentHandle(
        name="coder-1",
        config=SubAgentConfig(name="coder-1"),
        status=SubAgentStatus.RUNNING,
        task_preview="[SDD change=feat-x task=1.1]\nstill going",
    )
    mgr = MagicMock()
    mgr.list_active = MagicMock(return_value=[orphan])
    mgr.terminate = AsyncMock(side_effect=lambda name: name in {"coder-1", "coder-2"})
    parent.subagents = mgr

    cancel = await cancel_sdd_subagents_after_check(
        parent,
        project_root=tmp_path,
        change_id="feat-x",
        task_id="1.2",
        done=True,
        tasks_done=2,
        tasks_total=2,
    )
    assert set(cancel["cancelled_jobs"]) >= {"coder-1"}
    assert "coder-1" in cancel["cancel_requested"]
    assert "coder-2" in cancel["cancel_requested"]


@pytest.mark.asyncio
async def test_check_task_skips_followed_process_waiter(tmp_path: Path):
    store = SpecStore(tmp_path)
    _ready_change(store)
    write_task_job(tmp_path, "feat-x", "1.1", "python-coder")

    parent = MagicMock()
    parent.config = MagicMock()
    parent.config.workspace_root = str(tmp_path)

    waiter = SubAgentHandle(
        name="python-coder",
        config=SubAgentConfig(name="python-coder"),
        status=SubAgentStatus.RUNNING,
        task_preview="[SDD change=feat-x task=1.1]\nBackend work",
    )
    waiter.followed_process = True
    waiter.studio_process_id = "proc-dev"
    mgr = MagicMock()
    mgr.list_active = MagicMock(return_value=[waiter])
    mgr.get_handle = MagicMock(return_value=waiter)
    mgr.terminate = AsyncMock(return_value=True)
    parent.subagents = mgr

    result = store.check_task("feat-x", task_id="1.1", done=True)
    cancel = await cancel_sdd_subagents_after_check(
        parent,
        project_root=tmp_path,
        change_id="feat-x",
        task_id="1.1",
        done=True,
        tasks_done=result["tasks_done"],
        tasks_total=result["tasks_total"],
    )
    assert "python-coder" not in cancel["cancelled_jobs"]
    assert "python-coder" in cancel["skipped_process_jobs"]
    mgr.terminate.assert_not_awaited()
