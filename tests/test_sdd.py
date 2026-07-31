"""Spec-Driven Development (openspec layout) unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.sdd.apply_mode import apply_mode_prompt_text, normalize_apply_mode, save_apply_mode
from core.sdd.merge import merge_delta_into_main
from core.sdd.store import SpecStore
from core.sdd.tasks import parse_tasks_markdown, set_task_assignee, set_task_done


def test_parse_tasks_with_assignees():
    md = """
# Tasks

- [ ] 1.1 Add endpoints
  - **assignee:** `api-dev`
  - **reason:** isolated

- [x] 1.2 Wire config
  - **assignee:** main
"""
    tasks = parse_tasks_markdown(md)
    assert len(tasks) == 2
    assert tasks[0].id == "1.1"
    assert tasks[0].assignee == "api-dev"
    assert tasks[0].done is False
    assert tasks[0].reason == "isolated"
    assert tasks[1].id == "1.2"
    assert tasks[1].assignee == "main"
    assert tasks[1].done is True


def test_reject_and_normalize_freeform_tasks():
    from core.sdd.tasks import ensure_tasks_openspec_format, parse_tasks_markdown

    bad = """# Задачи: frontend

## 1. Подготовка проекта
- **Описание:** Создать директорию frontend/
- **Исполнитель:** coder
- **Результат:** package.json

## 2. UI layout
- **Описание:** AppLayout
- **Исполнитель:** coder
- **Результат:** навигация
"""
    assert parse_tasks_markdown(bad) == []
    fixed, notes = ensure_tasks_openspec_format(bad)
    assert notes
    tasks = parse_tasks_markdown(fixed)
    assert len(tasks) == 2
    assert tasks[0].id == "1.1"
    assert tasks[0].assignee == "coder"
    assert "- [ ] 1.1 " in fixed
    assert "**assignee:**" in fixed

    with pytest.raises(ValueError, match="OpenSpec"):
        ensure_tasks_openspec_format("# Empty\n\nNo tasks here.\n")


def test_write_artifact_tasks_auto_normalizes(tmp_path: Path):
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    store.create_change("fe", domain="auth")
    result = store.write_artifact(
        "fe",
        "tasks",
        """# Tasks: fe

## 1. Scaffold
- **Description:** Vite app
- **Assignee:** coder
- **Result:** package.json
""",
    )
    assert result["ok"] is True
    assert result["tasks_total"] == 1
    assert result["normalized"] is True
    tasks = store.list_tasks("fe")
    assert len(tasks) == 1
    assert tasks[0]["assignee"] == "coder"
    assert tasks[0]["id"] == "1.1"


def test_set_task_done_and_assignee():
    md = """# T

- [ ] 1.1 Foo
  - **assignee:** `unassigned`
"""
    md2 = set_task_done(md, task_id="1.1", done=True)
    assert "- [x] 1.1 Foo" in md2
    md3 = set_task_assignee(md2, task_id="1.1", assignee="ui-dev", reason="UI only")
    tasks = parse_tasks_markdown(md3)
    assert tasks[0].assignee == "ui-dev"
    assert tasks[0].reason == "UI only"
    assert tasks[0].done is True


def test_merge_delta_added_modified_removed():
    main = """# Auth

### Requirement: Login exists
The system SHALL support password login.

#### Scenario: Valid credentials
- **GIVEN** a user
- **WHEN** they login
- **THEN** a session is created

### Requirement: Logout exists
The system SHALL support logout.
"""
    delta = """
## ADDED Requirements

### Requirement: OAuth login
The system SHALL support OAuth.

#### Scenario: Provider redirect
- **GIVEN** OAuth configured
- **WHEN** user starts OAuth
- **THEN** they are redirected

## MODIFIED Requirements

### Requirement: Login exists
The system SHALL support password and OAuth login.

#### Scenario: Valid credentials
- **GIVEN** a user
- **WHEN** they login
- **THEN** a session is created

## REMOVED Requirements

### Requirement: Logout exists
"""
    out = merge_delta_into_main(main, delta)
    assert "OAuth login" in out
    assert "password and OAuth" in out
    assert "Logout exists" not in out
    assert out.count("### Requirement:") == 2


def test_merge_document_order_removed_wins_after_modified():
    main = "# D\n\n### Requirement: Foo\nOld\n"
    delta = """## MODIFIED Requirements

### Requirement: Foo
New body

## REMOVED Requirements

### Requirement: Foo
"""
    out = merge_delta_into_main(main, delta)
    assert "Foo" not in out
    assert "New body" not in out


def test_merge_collapses_duplicate_titles_in_main():
    main = """# D

### Requirement: Dup
First

### Requirement: Dup
Second
"""
    delta = """## MODIFIED Requirements

### Requirement: Dup
Third
"""
    out = merge_delta_into_main(main, delta)
    assert out.count("### Requirement:") == 1
    assert "Third" in out
    assert "First" not in out


def test_archive_nested_spec_merges_into_parent_domain(tmp_path: Path):
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    store.create_change("nested-merge", domain="auth")
    store.write_artifact(
        "nested-merge",
        "proposal",
        "# Proposal\n\n## Why\nNeed nested layout fix.\n\n## What\nMerge correctly.\n\n## Impact\nSpecs.\n",
    )
    store.write_artifact(
        "nested-merge",
        "specs",
        "## ADDED Requirements\n\n### Requirement: Top level\nBody top.\n\n#### Scenario: S\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n",
        domain="auth",
    )
    nested = (
        tmp_path
        / "openspec"
        / "changes"
        / "nested-merge"
        / "specs"
        / "auth"
        / "notes"
        / "spec.md"
    )
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text(
        "## ADDED Requirements\n\n### Requirement: Nested note\nBody nested.\n\n"
        "#### Scenario: S\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n",
        encoding="utf-8",
    )
    store.write_artifact(
        "nested-merge",
        "tasks",
        "# Tasks\n\n- [x] 1.1 Done\n  - **assignee:** `main`\n  - **reason:** ok\n",
    )
    archived = store.archive("nested-merge")
    assert archived["ok"] is True
    # Must NOT create openspec/specs/notes/
    assert not (tmp_path / "openspec" / "specs" / "notes").exists()
    main = (tmp_path / "openspec" / "specs" / "auth" / "spec.md").read_text(encoding="utf-8")
    assert "Top level" in main
    assert "Nested note" in main
    assert archived["merged_specs"] == ["openspec/specs/auth/spec.md"]


def test_archive_warns_on_open_tasks(tmp_path: Path):
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    store.create_change("open-tasks", domain="auth")
    store.write_artifact(
        "open-tasks",
        "proposal",
        "# Proposal\n\n## Why\nWhy enough for propose.\n\n## What\nWhat.\n\n## Impact\nImpact.\n",
    )
    store.write_artifact(
        "open-tasks",
        "specs",
        "## ADDED Requirements\n\n### Requirement: Open\nBody.\n\n#### Scenario: S\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n",
        domain="auth",
    )
    store.write_artifact(
        "open-tasks",
        "tasks",
        "# Tasks\n\n- [ ] 1.1 Still open\n  - **assignee:** `main`\n  - **reason:** work\n",
    )
    archived = store.archive("open-tasks")
    assert archived["ok"] is True
    assert archived.get("warnings")
    assert any("open task" in w.lower() for w in archived["warnings"])


def test_store_lifecycle(tmp_path: Path):
    store = SpecStore(tmp_path)
    init = store.init(example_domain="auth")
    assert init["ok"] is True
    assert (tmp_path / "openspec" / "config.yaml").is_file()
    assert (tmp_path / "openspec" / "specs" / "auth" / "spec.md").is_file()

    specs = store.list_specs()
    assert specs[0]["domain"] == "auth"

    created = store.create_change("oauth-login", domain="auth")
    assert created["change_id"] == "oauth-login"

    st = store.change_status("oauth-login")
    assert st.apply_ready is False  # empty proposal stub

    store.write_artifact(
        "oauth-login",
        "proposal",
        "# Proposal\n\n## Why\nNeed OAuth for enterprise SSO.\n\n## What\nAdd OAuth flow.\n\n## Impact\nAuth module.\n",
    )
    store.write_artifact(
        "oauth-login",
        "specs",
        "## ADDED Requirements\n\n### Requirement: OAuth\nThe system SHALL support OAuth.\n\n#### Scenario: OK\n- **GIVEN** x\n- **WHEN** y\n- **THEN** z\n",
        domain="auth",
    )
    # Stub tasks (assignee main) are enough for solo apply-ready
    st_stub_tasks = store.change_status("oauth-login")
    assert st_stub_tasks.apply_ready is True

    store.write_artifact(
        "oauth-login",
        "tasks",
        """# Tasks

- [ ] 1.1 Backend
  - **assignee:** `api-dev`
  - **reason:** API

- [ ] 1.2 Frontend
  - **assignee:** `main`
  - **reason:** shared UI shell
""",
    )
    st2 = store.change_status("oauth-login")
    assert st2.apply_ready is True
    assert st2.assignees["api-dev"] == 1
    assert st2.apply_mode is None

    req = store.request_apply_mode("oauth-login")
    assert req["already_set"] is False
    assert "self" in req["prompt"]

    blocked = store.begin_apply("oauth-login")
    assert blocked["ok"] is False
    assert blocked["need_user_choice"] is True

    store.set_apply_mode("oauth-login", "subagents")
    plan = store.begin_apply("oauth-login")
    assert plan["ok"] is True
    assert plan["apply_mode"] == "subagents"
    assert plan["plan"][0]["executor"] == "api-dev"
    assert plan["plan"][1]["executor"] == "main"

    store.check_task("oauth-login", task_id="1.1", done=True)
    store.check_task("oauth-login", task_id="1.2", done=True)

    archived = store.archive("oauth-login")
    assert archived["ok"] is True
    assert "openspec/specs/auth/spec.md" in archived["merged_specs"]
    main = (tmp_path / "openspec" / "specs" / "auth" / "spec.md").read_text()
    assert "OAuth" in main
    assert not (tmp_path / "openspec" / "changes" / "oauth-login").exists()
    assert any(
        p.name.endswith("oauth-login") or "oauth-login" in p.name
        for p in (tmp_path / "openspec" / "changes" / "archive").iterdir()
    )


def test_unassigned_tasks_ok_for_self_not_hybrid(tmp_path: Path):
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    store.create_change("feat-u", domain="auth")
    store.write_artifact(
        "feat-u",
        "proposal",
        "# Proposal\n\n## Why\nNeed it for users.\n\n## What\nShip feature.\n\n## Impact\nLow risk.\n",
    )
    store.write_artifact(
        "feat-u",
        "specs",
        "## ADDED Requirements\n\n### Requirement: Feat\nThe system SHALL do X.\n\n#### Scenario: OK\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n",
        domain="auth",
    )
    store.write_artifact(
        "feat-u",
        "tasks",
        """# Tasks

- [ ] 1.1 Do work
  - **assignee:** `unassigned`
""",
    )
    # Default / self: unassigned is fine (dispatch → main)
    assert store.change_status("feat-u").apply_ready is True
    store.set_apply_mode("feat-u", "self")
    plan = store.begin_apply("feat-u")
    assert plan["ok"] is True
    assert plan["plan"][0]["executor"] == "main"

    # hybrid maps unassigned → main
    store.set_apply_mode("feat-u", "hybrid")
    assert store.change_status("feat-u").apply_ready is True
    plan_h = store.begin_apply("feat-u")
    assert plan_h["ok"] is True
    assert plan_h["plan"][0]["executor"] == "main"

    # subagents still requires real assignees
    store.set_apply_mode("feat-u", "subagents")
    st = store.change_status("feat-u")
    assert st.apply_ready is False
    assert any("unassigned" in m for m in st.missing)
    blocked = store.begin_apply("feat-u")
    assert blocked["ok"] is False
    assert "1.1" in blocked["error"]

    assigned = store.assign_unassigned_tasks("feat-u", "main")
    assert assigned["count"] == 1
    assert store.change_status("feat-u").apply_ready is True


def test_apply_mode_normalize():
    assert normalize_apply_mode("Self") == "self"
    with pytest.raises(ValueError):
        normalize_apply_mode("parallel")
    text = apply_mode_prompt_text("x", assignees={"main": 1})
    assert "hybrid" in text


def test_save_apply_mode(tmp_path: Path):
    store = SpecStore(tmp_path)
    store.init()
    store.create_change("c1")
    save_apply_mode(tmp_path, "c1", "hybrid")
    assert store.change_status("c1").apply_mode == "hybrid"


def test_discover_multi_project_openspec(tmp_path: Path):
    from core.sdd.projects import discover_sdd_projects

    SpecStore(tmp_path / "alpha").init(example_domain="alpha")
    SpecStore(tmp_path / "beta" / "svc").init(example_domain="beta")
    (tmp_path / "noise").mkdir()
    (tmp_path / "noise" / "readme.txt").write_text("x", encoding="utf-8")

    projects = discover_sdd_projects(tmp_path)
    paths = {p["path"] for p in projects}
    assert "alpha" in paths
    assert "beta/svc" in paths
    assert "" not in paths  # root not initialized


def test_understanding_gate_cycle(tmp_path: Path):
    from core.sdd.understanding import (
        confirm_understanding,
        gate_blocks_propose,
        update_understanding,
    )

    store = SpecStore(tmp_path)
    store.init()
    created = store.create_change(
        "oauth",
        domain="auth",
        request="Add OAuth login",
        understanding_gate_enabled=True,
        understanding_threshold=80,
    )
    und = created["understanding"]
    assert und["enabled"] is True
    assert und["status"] == "clarifying"
    assert und["score"] == 0
    assert gate_blocks_propose(tmp_path, "oauth")

    low = update_understanding(
        tmp_path,
        "oauth",
        score=40,
        summary="Partial",
        questions=["Which providers?"],
        agent_note="Need provider list",
    )
    assert low["action"] == "clarify"
    assert low["understanding"]["status"] == "clarifying"

    ready = update_understanding(
        tmp_path,
        "oauth",
        score=85,
        summary="Clear enough",
        questions=[],
        agent_note="Understood",
    )
    assert ready["action"] == "ready"
    assert ready["understanding"]["status"] == "ready"
    assert "confirm" in (gate_blocks_propose(tmp_path, "oauth") or "").lower()

    drop = update_understanding(
        tmp_path,
        "oauth",
        score=50,
        summary="New ambiguity",
        questions=["Scope?"],
        user_answer="Also need SSO",
    )
    assert drop["action"] == "clarify"
    assert drop["understanding"]["status"] == "clarifying"

    update_understanding(tmp_path, "oauth", score=90, summary="SSO included")
    blocked = confirm_understanding(tmp_path, "oauth")
    # still need score after last update
    assert blocked["ok"] is True
    assert blocked["understanding"]["status"] == "confirmed"
    assert gate_blocks_propose(tmp_path, "oauth") is None


def test_understanding_gate_disabled_skips(tmp_path: Path):
    from core.sdd.understanding import gate_blocks_propose

    store = SpecStore(tmp_path)
    store.init()
    created = store.create_change(
        "simple",
        request="Do a thing",
        understanding_gate_enabled=False,
    )
    assert created["understanding"]["status"] == "skipped"
    assert created["understanding"]["score"] == 100
    assert gate_blocks_propose(tmp_path, "simple") is None


def test_accept_request_understanding_unlock_modes(tmp_path: Path):
    """unlock=False seeds request without forcing 100%; unlock=True confirms for fill."""
    from core.sdd.understanding import (
        accept_request_understanding,
        gate_blocks_propose,
        init_understanding,
        load_understanding,
    )

    store = SpecStore(tmp_path)
    store.init()
    store.create_change(
        "feat",
        request="Add feature X",
        understanding_gate_enabled=True,
        understanding_threshold=80,
    )
    und = load_understanding(tmp_path, "feat")
    assert und is not None
    assert und.status == "clarifying" and und.score == 0

    seeded = accept_request_understanding(
        tmp_path, "feat", request="Add feature X", unlock=False
    )
    assert seeded.status == "clarifying"
    assert seeded.score == 0
    assert gate_blocks_propose(tmp_path, "feat") is not None

    unlocked = accept_request_understanding(
        tmp_path, "feat", request="Add feature X", unlock=True
    )
    assert unlocked.status == "confirmed"
    assert unlocked.score >= unlocked.threshold
    assert gate_blocks_propose(tmp_path, "feat") is None

    # create with request already seeds history via init_understanding
    init_understanding(
        tmp_path, "other", enabled=True, threshold=75, request="Need Y"
    )
    other = load_understanding(tmp_path, "other")
    assert other is not None
    assert other.score == 0 and other.status == "clarifying"


@pytest.mark.asyncio
async def test_sdd_tools_register_and_init(tmp_path: Path):
    from core.tools.execution_context import reset_workspace_scope, workspace_scope
    from core.tools.registry import ToolRegistry

    tokens = workspace_scope(
        workspace_root=str(tmp_path),
        workspace_jail_enabled=False,
    )
    try:
        reg = ToolRegistry()
        reg.register_all()
        assert "sdd_init" in reg.tools
        assert "sdd_apply" in reg.tools
        assert "sdd_request_apply_mode" in reg.tools
        result = await reg.tools["sdd_init"].execute()
        assert '"ok"' in result
        assert (tmp_path / "openspec" / "config.yaml").is_file()
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_nested_project_paths_and_read_file_hint(tmp_path: Path):
    """Nested SDD must report workspace-relative paths (project prefix)."""
    import json

    from core.tools.execution_context import reset_workspace_scope, workspace_scope
    from core.tools.file_ops import ReadFileTool
    from core.tools.registry import ToolRegistry

    project = tmp_path / "user_catalog"
    project.mkdir()
    store = SpecStore(project)
    store.init(example_domain="user_catalog")
    store.create_change("test-1", domain="user_catalog", request="demo")

    # Jail on so resolve_tool_path uses workspace root (not cwd).
    tokens = workspace_scope(
        workspace_root=str(tmp_path),
        workspace_jail_enabled=True,
    )
    try:
        # Paths for tools include project prefix
        assert store.tool_relpath(project / "openspec/changes/test-1/tasks.md") == (
            "user_catalog/openspec/changes/test-1/tasks.md"
        )
        reg = ToolRegistry()
        reg.register_all()
        status_raw = await reg.tools["sdd_status"].execute(
            project="user_catalog", change_id="test-1"
        )
        status = json.loads(status_raw)
        assert status["ok"] is True
        assert status["artifact_paths"]["tasks"] == (
            "user_catalog/openspec/changes/test-1/tasks.md"
        )
        assert status["path"] == "user_catalog/openspec/changes/test-1"

        # Wrong workspace-root path → hint with correct nested path
        read = ReadFileTool()
        bad = await read.execute("openspec/changes/test-1/tasks.md")
        assert "does not exist" in bad
        assert "user_catalog/openspec/changes/test-1/tasks.md" in bad

        # Correct path works
        good = await read.execute("user_catalog/openspec/changes/test-1/tasks.md")
        assert "does not exist" not in good
        assert "Tasks" in good or "tasks" in good.lower() or "# " in good
    finally:
        reset_workspace_scope(tokens)


def test_resolve_delta_domain_prefers_existing_over_example(tmp_path: Path):
    project = tmp_path / "user_catalog"
    project.mkdir()
    store = SpecStore(project)
    store.init(example_domain="user_catalog")
    # Wrong preferred domain must not invent a new delta domain
    assert store.resolve_delta_domain("example") == "user_catalog"
    assert store.resolve_delta_domain("new-user") == "user_catalog"
    assert store.resolve_delta_domain("user_catalog") == "user_catalog"
    created = store.create_change("watcher", domain="example")
    assert created["domain"] == "user_catalog"
    assert (project / "openspec/changes/watcher/specs/user_catalog/spec.md").is_file()
    assert not (project / "openspec/changes/watcher/specs/example").exists()
    assert not (project / "openspec/changes/watcher/specs/new-user").exists()


def test_resolve_delta_domain_project_name_when_empty(tmp_path: Path):
    project = tmp_path / "billing-api"
    project.mkdir()
    store = SpecStore(project)
    # Initialized but no domain specs yet
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / "config.yaml").write_text("schema: holix-spec\n", encoding="utf-8")
    (store.root / "specs").mkdir(parents=True, exist_ok=True)
    (store.root / "changes").mkdir(parents=True, exist_ok=True)
    assert store.list_specs() == []
    assert store.project_domain_slug() == "billing-api"
    assert store.resolve_delta_domain("example") == "billing-api"
    created = store.create_change("add-invoice", domain="example")
    assert created["domain"] == "billing-api"
    assert (project / "openspec/changes/add-invoice/specs/billing-api/spec.md").is_file()


def test_resolve_delta_domain_multiple_existing(tmp_path: Path):
    project = tmp_path / "mono"
    project.mkdir()
    store = SpecStore(project)
    store.init(example_domain="alpha")
    (project / "openspec/specs/beta").mkdir(parents=True)
    (project / "openspec/specs/beta/spec.md").write_text("# beta\n", encoding="utf-8")
    assert store.resolve_delta_domain("beta") == "beta"
    assert store.resolve_delta_domain("") == "alpha"  # first sorted
