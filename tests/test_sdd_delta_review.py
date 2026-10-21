"""Spec delta review, archive guards, skip_specs, and done_when."""

from pathlib import Path

from core.sdd.store import SpecStore
from core.sdd.tasks import parse_tasks_markdown

_PROPOSAL = (
    "# Proposal\n\n## Why\nNeed it for users.\n\n## What\nShip the change.\n\n## Impact\nAuth.\n"
)


def _ready_tasks(done: bool = False) -> str:
    mark = "x" if done else " "
    return (
        "# Tasks\n\n"
        f"- [{mark}] 1.1 Token endpoint\n"
        "  - **assignee:** `main`\n"
        "  - **size:** `s`\n"
        "  - **done_when:** pytest tests/test_auth.py passes\n"
    )


def test_done_when_roundtrip() -> None:
    tasks = parse_tasks_markdown(_ready_tasks())
    assert tasks[0].done_when == "pytest tests/test_auth.py passes"


def test_status_diffs_modified_requirement_and_names_next(tmp_path: Path) -> None:
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    main = tmp_path / "openspec" / "specs" / "auth" / "spec.md"
    main.write_text(
        "# auth\n\n"
        "### Requirement: Login\n"
        "The system SHALL accept a password.\n\n"
        "#### Scenario: Happy path\n"
        "- **THEN** a session exists\n\n"
        "#### Scenario: Locked account\n"
        "- **THEN** login is refused\n",
        encoding="utf-8",
    )
    store.create_change("tighten-login", domain="auth")
    store.write_artifact("tighten-login", "proposal", _PROPOSAL)
    store.write_artifact(
        "tighten-login",
        "specs",
        "## MODIFIED Requirements\n\n"
        "### Requirement: Login\n"
        "The system SHALL accept a password.\n\n"
        "#### Scenario: Happy path\n"
        "- **THEN** a session exists\n\n"
        "## Notes\n\nThis heading is not a delta section.\n",
        domain="auth",
    )
    store.write_artifact("tighten-login", "tasks", _ready_tasks(done=True))
    view = store.change_view("tighten-login")
    review = view["delta_review"]
    assert review["requirements"][0]["op"] == "MODIFIED"
    assert "Locked account" in review["requirements"][0]["scenarios_lost"]
    assert any("drops scenario" in item for item in review["warnings"])
    assert any("will not merge" in item for item in review["warnings"])
    assert "ready to archive" in view["next"]
    assert view["tasks_complete"] is True
    assert view["task_warnings"] == []


def test_archive_refuses_case_only_title(tmp_path: Path) -> None:
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    main = tmp_path / "openspec" / "specs" / "auth" / "spec.md"
    original = (
        "# auth\n\n### Requirement: Login\nThe system SHALL keep this title.\n\n"
        "#### Scenario: OK\n- **THEN** ok\n"
    )
    main.write_text(original, encoding="utf-8")
    store.create_change("rename-case", domain="auth")
    store.write_artifact("rename-case", "proposal", _PROPOSAL)
    store.write_artifact(
        "rename-case",
        "specs",
        "## MODIFIED Requirements\n\n### Requirement: login\nThe system SHALL change case.\n",
        domain="auth",
    )
    store.write_artifact("rename-case", "tasks", _ready_tasks(done=True))
    archived = store.archive("rename-case")
    assert archived["ok"] is False
    assert "case" in archived["error"]
    assert main.read_text(encoding="utf-8") == original
    assert (tmp_path / "openspec" / "changes" / "rename-case").is_dir()


def test_skip_specs_archives_without_merging_stubs(tmp_path: Path) -> None:
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    main = tmp_path / "openspec" / "specs" / "auth" / "spec.md"
    before = main.read_text(encoding="utf-8")
    store.create_change("docs-only", domain="auth", skip_specs=True)
    store.write_artifact("docs-only", "proposal", _PROPOSAL)
    store.write_artifact("docs-only", "tasks", _ready_tasks(done=True))
    status = store.change_status("docs-only")
    assert status.skip_specs is True
    assert status.apply_ready is True
    archived = store.archive("docs-only")
    assert archived["ok"] is True, archived
    assert archived["requirements_merged"] == 0
    assert main.read_text(encoding="utf-8") == before
    assert not (tmp_path / "openspec" / "changes" / "docs-only").exists()


def test_prose_spec_is_not_apply_ready(tmp_path: Path) -> None:
    store = SpecStore(tmp_path)
    store.init(example_domain="auth")
    store.create_change("prose", domain="auth")
    store.write_artifact("prose", "proposal", _PROPOSAL)
    store.write_artifact(
        "prose",
        "specs",
        "# Notes\n\nThis change describes the work in prose only, with no requirement blocks.\n",
        domain="auth",
    )
    store.write_artifact("prose", "tasks", _ready_tasks())
    status = store.change_status("prose")
    assert status.apply_ready is False
    assert any("skip_specs" in item for item in status.missing)
