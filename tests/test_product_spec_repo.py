"""Studio multi-repo product: dedicated spec clone vs code clones."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core.sdd.change_workspace import (
    bind_active_change,
    compose_active_change,
    file_workspace_root,
    format_active_change_prompt_block,
    get_active_change,
    inherit_active_change,
    overlay_workspace_root,
    reset_active_change_store,
)
from core.sdd.product_change_id import allocate_product_change_id
from core.sdd.product_layout import load_product_layout
from core.sdd.projects import discover_sdd_projects
from core.tools.execution_context import (
    conversation_scope,
    get_workspace_root,
    profile_scope,
    reset_conversation_scope,
    reset_profile_scope,
    reset_workspace_scope,
    workspace_scope,
)


def _write_product(tmp: Path) -> Path:
    root = tmp / "acme"
    (root / ".holix").mkdir(parents=True)
    (root / "api").mkdir()
    (root / "web").mkdir()
    (root / "spec").mkdir()
    (root / "api" / "main.py").write_text("print(1)\n", encoding="utf-8")
    data = {
        "id": "proj_acme",
        "name": "Acme",
        "slug": "acme",
        "workspace_rel": "acme",
        "settings": {"task_prefix": "acme", "task_seq": 2},
        "repos": [
            {"id": "api", "name": "api", "path": "api", "role": "code"},
            {"id": "web", "name": "web", "path": "web", "role": "code"},
            {"id": "spec", "name": "spec", "path": "spec", "role": "spec"},
        ],
        "tasks": [],
    }
    (root / ".holix" / "project.json").write_text(json.dumps(data), encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _reset_pins() -> None:
    reset_active_change_store()
    yield
    reset_active_change_store()


def test_multi_repo_worktree_pin_keeps_product_file_root(tmp_path: Path) -> None:
    root = _write_product(tmp_path)
    wt = root / "spec" / ".holix" / "worktrees" / "acme-3"
    wt.mkdir(parents=True)
    active = compose_active_change(
        change_id="acme-3",
        worktree=str(wt),
        clone=str(root / "spec"),
        project="acme",
    )
    assert Path(active.project_root) == root.resolve()
    assert active.worktree == str(wt)
    bind_active_change("default", "sess_sdd", active)
    assert overlay_workspace_root("default", "sess_sdd") == str(root.resolve())
    child = inherit_active_change("default", "sess_sdd", "subagent:sess_sdd:coder")
    assert child is not None
    assert Path(child.worktree) == wt.resolve() or child.worktree == str(wt)
    assert overlay_workspace_root("default", "subagent:sess_sdd:coder") == str(root.resolve())
    assert file_workspace_root(child) == str(root.resolve())
    block = format_active_change_prompt_block(child)
    assert "multi-repo" in block.lower()
    assert "spec worktree" in block.lower()
    assert str(root.resolve()) in block
    assert "openspec" in block.lower()


def test_layout_resolves_spec_and_code(tmp_path: Path) -> None:
    root = _write_product(tmp_path)
    layout = load_product_layout(root / "api")
    assert layout is not None
    assert layout.has_dedicated_spec
    assert layout.spec_root == (root / "spec").resolve()
    assert (root / "api").resolve() in layout.code_roots


def test_no_roles_is_not_dedicated(tmp_path: Path) -> None:
    root = tmp_path / "solo"
    (root / ".holix").mkdir(parents=True)
    (root / ".holix" / "project.json").write_text(
        json.dumps(
            {
                "id": "p",
                "slug": "solo",
                "repos": [{"id": "r1", "name": "bot", "path": "solo"}],
            }
        ),
        encoding="utf-8",
    )
    layout = load_product_layout(root)
    assert layout is not None
    assert layout.has_dedicated_spec is False
    assert layout.spec_root is None


def test_allocate_puts_changes_in_spec_repo(tmp_path: Path) -> None:
    root = _write_product(tmp_path)
    out = allocate_product_change_id(root / "api", requested="free-form-slug")
    assert out is not None
    assert out["change_id"] == "acme-3"
    assert (root / "spec" / "openspec" / "changes" / "acme-3").exists() is False
    # allocate does not mkdir dest when rewritten from seq; dest check only for matching id
    out2 = allocate_product_change_id(root, requested="acme-4")
    assert out2 is not None
    assert out2["change_id"] == "acme-4"


def test_discover_lists_only_spec_repo(tmp_path: Path) -> None:
    root = _write_product(tmp_path)
    from core.sdd.store import SpecStore

    SpecStore(root / "spec").init(example_domain="acme")
    SpecStore(root / "api").init(example_domain="wrong")
    found = discover_sdd_projects(root)
    assert len(found) == 1
    assert found[0]["role"] == "spec"
    assert found[0]["path"] == "spec"


@pytest.mark.asyncio
async def test_sdd_init_goes_to_spec_repo_not_code_clone(tmp_path: Path) -> None:
    from core.tools.registry import ToolRegistry

    root = _write_product(tmp_path)
    tokens = workspace_scope(workspace_root=str(root), workspace_jail_enabled=True)
    ptok = profile_scope("default")
    ctok = conversation_scope("p1")
    try:
        reg = ToolRegistry(workspace_root=str(root), profile_name="default")
        reg.register_all()
        data = json.loads(await reg.tools["sdd_init"].execute())
        assert data.get("ok") is True
        assert Path(data["spec_repo"]) == (root / "spec").resolve()
        assert (root / "spec" / "openspec" / "config.yaml").is_file()
        assert not (root / "openspec" / "config.yaml").exists()
        assert not (root / "api" / "openspec").exists()
        assert get_workspace_root() == str(root.resolve())
        active = get_active_change("default", "p1")
        assert active is not None
        assert Path(active.project_root) == root.resolve()

        refused = json.loads(await reg.tools["sdd_init"].execute(project="api"))
        assert refused.get("ok") is False
        assert "spec" in (refused.get("error") or "").lower()

        created = json.loads(
            await reg.tools["sdd_create_change"].execute(
                change_id="anything", request="shared spec"
            )
        )
        assert created.get("ok") is True
        cid = created["change_id"]
        assert (root / "spec" / "openspec" / "changes" / cid / "proposal.md").is_file()
        assert not (root / "api" / "openspec").exists()
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_sdd_init_from_code_clone_workspace_redirects(tmp_path: Path) -> None:
    from core.tools.registry import ToolRegistry

    root = _write_product(tmp_path)
    api = root / "api"
    tokens = workspace_scope(workspace_root=str(api), workspace_jail_enabled=True)
    ptok = profile_scope("default")
    ctok = conversation_scope("p2")
    try:
        reg = ToolRegistry(workspace_root=str(api), profile_name="default")
        reg.register_all()
        data = json.loads(await reg.tools["sdd_init"].execute())
        assert data.get("ok") is True
        assert (root / "spec" / "openspec" / "config.yaml").is_file()
        assert not (api / "openspec").exists()
        assert get_workspace_root() == str(root.resolve())
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)


def _write_multi_no_roles(tmp: Path, *, openspec_in: str | None = "backend") -> Path:
    root = tmp / "shop"
    (root / ".holix").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "backend").mkdir()
    data = {
        "id": "proj_shop",
        "name": "Shop",
        "slug": "shop",
        "workspace_rel": "shop",
        "settings": {"task_prefix": "shop", "task_seq": 0},
        "repos": [
            {"id": "fe", "name": "frontend", "path": "frontend"},
            {"id": "be", "name": "backend", "path": "backend"},
        ],
        "tasks": [],
    }
    (root / ".holix" / "project.json").write_text(json.dumps(data), encoding="utf-8")
    if openspec_in:
        from core.sdd.store import SpecStore

        SpecStore(root / openspec_in).init(example_domain="shop")
    return root


def test_inferred_openspec_root_without_spec_role(tmp_path: Path) -> None:
    root = _write_multi_no_roles(tmp_path, openspec_in="backend")
    layout = load_product_layout(root / "frontend")
    assert layout is not None
    assert layout.has_dedicated_spec is False
    assert layout.inferred_openspec_root() == (root / "backend").resolve()


@pytest.mark.asyncio
async def test_sdd_without_spec_mark_uses_existing_openspec_clone(
    tmp_path: Path,
) -> None:
    from core.tools.registry import ToolRegistry

    root = _write_multi_no_roles(tmp_path, openspec_in="backend")
    tokens = workspace_scope(workspace_root=str(root), workspace_jail_enabled=True)
    ptok = profile_scope("default")
    ctok = conversation_scope("p3")
    try:
        reg = ToolRegistry(workspace_root=str(root), profile_name="default")
        reg.register_all()
        listed = json.loads(await reg.tools["sdd_list_projects"].execute())
        paths = {p["path"] for p in listed.get("projects") or []}
        assert "backend" in paths
        created = json.loads(
            await reg.tools["sdd_create_change"].execute(
                change_id="anything", request="legacy openspec clone"
            )
        )
        assert created.get("ok") is True
        cid = created["change_id"]
        assert (root / "backend" / "openspec" / "changes" / cid / "proposal.md").is_file()
        assert not (root / "frontend" / "openspec").exists()
        assert not (root / "openspec").exists()
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_sdd_init_refuses_multi_without_spec_or_openspec(tmp_path: Path) -> None:
    from core.tools.registry import ToolRegistry

    root = _write_multi_no_roles(tmp_path, openspec_in=None)
    tokens = workspace_scope(workspace_root=str(root), workspace_jail_enabled=True)
    ptok = profile_scope("default")
    ctok = conversation_scope("p4")
    try:
        reg = ToolRegistry(workspace_root=str(root), profile_name="default")
        reg.register_all()
        refused_root = json.loads(await reg.tools["sdd_init"].execute())
        assert refused_root.get("ok") is False
        assert "role=spec" in (refused_root.get("error") or "")
        refused_fe = json.loads(await reg.tools["sdd_init"].execute(project="frontend"))
        assert refused_fe.get("ok") is False
        assert not (root / "openspec").exists()
        assert not (root / "frontend" / "openspec").exists()
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)
