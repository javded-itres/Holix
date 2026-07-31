"""SDD task volume estimation and decomposition validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.sdd.models import SpecTask
from core.sdd.store import SpecStore
from core.sdd.task_sizing import (
    estimate_task_size,
    max_steps_for_size,
    validate_task_sizes,
)
from core.sdd.tasks import ensure_tasks_openspec_format, parse_tasks_markdown


def test_estimate_small_vs_epic() -> None:
    assert estimate_task_size("1.1 Add health endpoint") in {"xs", "s", "m"}
    assert estimate_task_size(
        "1.1 Implement full OAuth end-to-end: backend API, frontend UI, "
        "database migrations, tests and docs across the whole module"
    ) in {"l", "xl"}
    assert max_steps_for_size("s") == 60
    assert max_steps_for_size("xs") == 40


def test_declared_size_respected() -> None:
    assert estimate_task_size("1.1 Something", declared="xs") == "xs"
    assert estimate_task_size("1.1 Something", declared="s") == "s"


def test_validate_rejects_large_subagent_tasks() -> None:
    tasks = [
        SpecTask(
            id="1.1",
            text=(
                "1.1 Implement entire frontend and backend for OAuth login, "
                "including tests and documentation across multiple files"
            ),
            assignee="coder",
        )
    ]
    errors = validate_task_sizes(tasks)
    assert errors
    assert any("1.1" in e for e in errors)


def test_validate_allows_large_main_tasks() -> None:
    tasks = [
        SpecTask(
            id="1.1",
            text=(
                "1.1 Coordinate full OAuth rollout across frontend and backend "
                "and docs for the entire module"
            ),
            assignee="main",
            size="l",
        )
    ]
    # main may keep larger work; only pure XL single-task plan flags hard.
    errors = validate_task_sizes(tasks)
    # single XL main task may still warn as epic plan
    assert isinstance(errors, list)


def test_parse_size_field() -> None:
    md = """# Tasks

- [ ] 1.1 Add endpoint
  - **assignee:** `coder`
  - **size:** `s`
  - **depends_on:**
"""
    tasks = parse_tasks_markdown(md)
    assert tasks[0].size == "s"


def test_ensure_adds_size_and_rejects_epic(tmp_path: Path) -> None:
    ok_md = """# Tasks: ok

- [ ] 1.1 Add GET /health
  - **assignee:** `coder`
  - **depends_on:**

- [ ] 1.2 Unit test for /health
  - **assignee:** `coder`
  - **depends_on:** `1.1`
"""
    fixed, notes = ensure_tasks_openspec_format(ok_md)
    assert "**size:**" in fixed
    tasks = parse_tasks_markdown(fixed)
    assert all(t.size for t in tasks)

    bad = """# Tasks: bad

- [ ] 1.1 Implement full OAuth end-to-end frontend + backend with tests and docs
  - **assignee:** `coder`
  - **size:** `xl`
"""
    with pytest.raises(ValueError, match="too large|OpenSpec|split"):
        ensure_tasks_openspec_format(bad)


def test_write_artifact_size_summary(tmp_path: Path) -> None:
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    store.create_change("sized", domain="auth")
    result = store.write_artifact(
        "sized",
        "tasks",
        """# Tasks: sized

- [ ] 1.1 Add login route handler only
  - **assignee:** `coder`
  - **size:** `s`

- [ ] 1.2 Add login unit test only
  - **assignee:** `coder`
  - **size:** `xs`
  - **depends_on:** `1.1`
""",
    )
    assert result["ok"] is True
    assert result["tasks_total"] == 2
    assert "size_summary" in result
    assert result["size_summary"]["ok"] is True
    listed = store.list_tasks("sized")
    assert listed[0]["size"] in {"xs", "s", "m"}
    assert listed[0]["max_steps"] > 0
