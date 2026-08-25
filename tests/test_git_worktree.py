"""Git worktrees for SDD changes."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from core.runtime.git_worktree import (
    WorktreeDirtyError,
    WorktreeLimitError,
    add_change_worktree,
    clone_root,
    extra_sandbox_write_roots,
    git_common_dir,
    list_holix_worktrees,
    prepare_change_worktree,
    prune_clone_worktrees,
    release_change_worktree,
    remove_change_worktree,
    worktrees_enabled,
)
from core.sdd.change_workspace import (
    bind_active_change,
    format_active_change_line,
    get_active_change,
    overlay_workspace_root,
    reset_active_change_store,
)
from core.tools.execution_context import (
    conversation_scope,
    get_workspace_root,
    profile_scope,
    reset_conversation_scope,
    reset_profile_scope,
    reset_workspace_scope,
    workspace_scope,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "app"
    repo.mkdir()
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo


def test_worktrees_enabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_WORKTREE", "0")
    assert worktrees_enabled() is False
    monkeypatch.setenv("HOLIX_WORKTREE", "1")
    assert worktrees_enabled() is True


def test_add_two_changes_leaves_main(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
    ).strip()
    a = add_change_worktree(repo, "itres-1")
    b = add_change_worktree(repo, "itres-2")
    assert a.worktree != b.worktree
    assert a.branch == "change/itres-1"
    assert (a.worktree / "README.md").is_file()
    head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
    ).strip()
    assert head == before
    trees = list_holix_worktrees(repo)
    assert {t.change_id for t in trees} == {"itres-1", "itres-2"}
    ignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".holix/worktrees/" in ignore


def test_prepare_skips_non_git(tmp_path: Path) -> None:
    assert prepare_change_worktree(tmp_path, "x-1") is None


def test_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_GIT_WORKTREES_MAX", "1")
    from config import settings

    monkeypatch.setattr(settings, "git_worktrees_max", 1)
    repo = _repo(tmp_path)
    add_change_worktree(repo, "one")
    with pytest.raises(WorktreeLimitError):
        add_change_worktree(repo, "two")


def test_sandbox_roots_include_common_dir(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    info = add_change_worktree(repo, "wt-1")
    extra = extra_sandbox_write_roots(str(info.worktree))
    assert extra
    common = git_common_dir(info.worktree)
    assert common is not None
    assert str(common) in extra
    assert clone_root(info.worktree) == repo.resolve()


def test_bind_overlays_workspace_root(tmp_path: Path) -> None:
    reset_active_change_store()
    repo = _repo(tmp_path)
    info = add_change_worktree(repo, "bind-1")
    bind_active_change("default", "conv-a", info)
    tokens = workspace_scope(workspace_root=str(repo), workspace_jail_enabled=False)
    ptok = profile_scope("default")
    ctok = conversation_scope("conv-a")
    try:
        assert get_workspace_root() == str(info.worktree)
        assert overlay_workspace_root("default", "conv-a") == str(info.worktree)
        assert "bind-1" in format_active_change_line(get_active_change("default", "conv-a"))
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)
        reset_active_change_store()


@pytest.mark.asyncio
async def test_sdd_create_change_tool_makes_worktree(tmp_path: Path) -> None:
    reset_active_change_store()
    repo = _repo(tmp_path)
    from core.tools.registry import ToolRegistry

    tokens = workspace_scope(workspace_root=str(repo), workspace_jail_enabled=False)
    ptok = profile_scope("default")
    ctok = conversation_scope("c1")
    try:
        reg = ToolRegistry(workspace_root=str(repo), profile_name="default")
        reg.register_all()
        init = await reg.tools["sdd_init"].execute()
        assert '"ok"' in init
        import json

        raw = await reg.tools["sdd_create_change"].execute(change_id="feat-wt", request="do it")
        data = json.loads(raw)
        assert data.get("ok") is True
        wt = Path(data["worktree"])
        assert wt.is_dir()
        assert (wt / "openspec" / "changes" / "feat-wt" / "proposal.md").is_file()
        assert not (repo / "openspec" / "changes" / "feat-wt").exists()
        assert get_active_change("default", "c1") is not None
        assert get_workspace_root() == str(wt)
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)
        reset_active_change_store()


def _fill_archiveable(store, change_id: str, domain: str = "auth") -> None:
    store.init(example_domain=domain)
    store.create_change(change_id, domain=domain)
    store.write_artifact(
        change_id,
        "proposal",
        "# Proposal\n\n## Why\nNeed it.\n\n## What\nShip it.\n\n## Impact\nSpecs.\n",
    )
    store.write_artifact(
        change_id,
        "specs",
        "## ADDED Requirements\n\n### Requirement: Archived bit\nBody.\n\n"
        "#### Scenario: S\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n",
        domain=domain,
    )
    store.write_artifact(
        change_id,
        "tasks",
        "# Tasks\n\n- [x] 1.1 Done\n  - **assignee:** `main`\n  - **reason:** ok\n",
    )


def test_dirty_paths_parse_one_and_two_space_porcelain(tmp_path: Path) -> None:
    from core.runtime.git_worktree import dirty_paths

    repo = _repo(tmp_path)
    (repo / "extra.txt").write_text("x\n", encoding="utf-8")
    (repo / "openspec").mkdir()
    (repo / "openspec" / "a.md").write_text("a\n", encoding="utf-8")
    paths = dirty_paths(repo)
    assert any(p.replace("\\", "/").startswith("openspec") for p in paths)
    assert any(p.endswith("extra.txt") or p == "extra.txt" for p in paths)


def test_remove_refuses_dirty_worktree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    info = add_change_worktree(repo, "dirty-1")
    (info.worktree / "wip.txt").write_text("keep me\n", encoding="utf-8")
    with pytest.raises(WorktreeDirtyError):
        remove_change_worktree(repo, "dirty-1", force=False)
    assert info.worktree.is_dir()
    assert (info.worktree / "wip.txt").is_file()


def test_archive_removes_clean_worktree(tmp_path: Path) -> None:
    from core.sdd.store import SpecStore

    repo = _repo(tmp_path)
    info = add_change_worktree(repo, "feat-arc")
    store = SpecStore(info.worktree)
    _fill_archiveable(store, "feat-arc")
    archived = store.archive("feat-arc")
    assert archived["ok"] is True
    released = release_change_worktree(info.worktree, "feat-arc", profile="default")
    assert released["removed"] is True, released
    assert released.get("committed") is True
    assert not info.worktree.exists()
    trees = list_holix_worktrees(repo)
    assert all(t.change_id != "feat-arc" for t in trees)
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "change/feat-arc"],
            check=False,
        ).returncode
        == 0
    )


def test_archive_keeps_dirty_non_openspec(tmp_path: Path) -> None:
    from core.sdd.store import SpecStore

    repo = _repo(tmp_path)
    info = add_change_worktree(repo, "feat-wip")
    store = SpecStore(info.worktree)
    _fill_archiveable(store, "feat-wip")
    (info.worktree / "notes.txt").write_text("uncommitted code\n", encoding="utf-8")
    archived = store.archive("feat-wip")
    assert archived["ok"] is True
    released = release_change_worktree(info.worktree, "feat-wip")
    assert released["removed"] is False
    assert released["reason"] == "dirty"
    assert info.worktree.is_dir()
    assert (info.worktree / "notes.txt").is_file()


def test_prune_over_max_drops_archived_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from config import settings

    monkeypatch.setattr(settings, "git_worktrees_max", 8)
    repo = _repo(tmp_path)
    a = add_change_worktree(repo, "old-a")
    b = add_change_worktree(repo, "old-b")
    keep = add_change_worktree(repo, "live-c")
    for info, cid in ((a, "old-a"), (b, "old-b")):
        arch = info.worktree / "openspec" / "changes" / "archive" / f"2026-08-26-{cid}"
        arch.mkdir(parents=True)
        (arch / "proposal.md").write_text("done\n", encoding="utf-8")
        _git(info.worktree, "add", "-A")
        _git(info.worktree, "commit", "--no-gpg-sign", "-m", f"archive {cid}")
    (keep.worktree / "openspec" / "changes" / "live-c").mkdir(parents=True)
    (keep.worktree / "openspec" / "changes" / "live-c" / "proposal.md").write_text(
        "wip\n", encoding="utf-8"
    )
    out = prune_clone_worktrees(repo, max_keep=1)
    ids = {t.change_id for t in list_holix_worktrees(repo)}
    assert "live-c" in ids
    assert "old-a" not in ids
    assert "old-b" not in ids
    assert set(out["removed"]) == {"old-a", "old-b"}


@pytest.mark.asyncio
async def test_sdd_archive_tool_releases_worktree(tmp_path: Path) -> None:
    reset_active_change_store()
    repo = _repo(tmp_path)
    from core.sdd.store import SpecStore
    from core.tools.registry import ToolRegistry

    tokens = workspace_scope(workspace_root=str(repo), workspace_jail_enabled=False)
    ptok = profile_scope("default")
    ctok = conversation_scope("c-arc")
    try:
        reg = ToolRegistry(workspace_root=str(repo), profile_name="default")
        reg.register_all()
        init = await reg.tools["sdd_init"].execute()
        assert '"ok"' in init
        raw = await reg.tools["sdd_create_change"].execute(
            change_id="tool-arc", request="archive me"
        )
        data = json.loads(raw)
        assert data.get("ok") is True
        wt = Path(data["worktree"])
        store = SpecStore(wt)
        domain = "example"
        spec_dir = wt / "openspec" / "specs"
        domains = [p.name for p in spec_dir.iterdir()] if spec_dir.is_dir() else []
        if domains:
            domain = domains[0]
        store.write_artifact(
            "tool-arc",
            "proposal",
            "# Proposal\n\n## Why\nNeed it.\n\n## What\nShip it.\n\n## Impact\nSpecs.\n",
        )
        store.write_artifact(
            "tool-arc",
            "specs",
            "## ADDED Requirements\n\n### Requirement: Tool archive\nBody.\n\n"
            "#### Scenario: S\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n",
            domain=domain,
        )
        store.write_artifact(
            "tool-arc",
            "tasks",
            "# Tasks\n\n- [x] 1.1 Done\n  - **assignee:** `main`\n  - **reason:** ok\n",
        )
        out = await reg.tools["sdd_archive"].execute(change_id="tool-arc")
        payload = json.loads(out)
        assert payload.get("ok") is True, payload
        wt_info = payload.get("worktree") or {}
        assert wt_info.get("removed") is True, payload
        assert not wt.exists()
        assert get_active_change("default", "c-arc") is None
    finally:
        reset_conversation_scope(ctok)
        reset_profile_scope(ptok)
        reset_workspace_scope(tokens)
        reset_active_change_store()
