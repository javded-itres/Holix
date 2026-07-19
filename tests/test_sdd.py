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
    assert gate_blocks_propose(tmp_path, "simple") is None


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
