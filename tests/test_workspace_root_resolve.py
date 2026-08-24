"""resolve_project_root prefers agent workspace over process CWD."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from core.project.planning_context import ensure_planning_context
from core.project.scan_safety import is_unsafe_project_scan_root
from core.project.workspace_root import profile_workspace_cwd, resolve_project_root


def test_resolve_prefers_agent_workspace_over_cwd(tmp_path, monkeypatch) -> None:
    launch = tmp_path / "launch"
    workspace = tmp_path / "workspace"
    launch.mkdir()
    workspace.mkdir()
    monkeypatch.chdir(launch)

    agent = SimpleNamespace(config=SimpleNamespace(workspace_root=str(workspace)))
    root = resolve_project_root(agent=agent)
    assert root == workspace.resolve()
    assert root != launch.resolve()


def test_resolve_ignores_magicmock_workspace(tmp_path, monkeypatch) -> None:
    """MagicMock agent.config must not invent a filesystem root."""
    monkeypatch.chdir(tmp_path)
    agent = MagicMock()
    root = resolve_project_root(agent=agent, host=MagicMock())
    assert root == tmp_path.resolve()
    assert not any(tmp_path.iterdir()) or all("MagicMock" not in p.name for p in tmp_path.iterdir())


def test_planning_init_writes_holix_in_workspace_not_cwd(tmp_path, monkeypatch) -> None:
    launch = tmp_path / "launch"
    workspace = tmp_path / "workspace"
    launch.mkdir()
    workspace.mkdir()
    (workspace / "README.md").write_text("# proj\n", encoding="utf-8")
    (workspace / "package.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.chdir(launch)

    ctx = ensure_planning_context(cwd=workspace, locale="en")
    assert ctx.init_ran is True
    holix = workspace / ".holix" / "HOLIX.md"
    assert holix.is_file()
    assert not (launch / ".holix" / "HOLIX.md").exists()
    assert "proj" in holix.read_text(encoding="utf-8") or holix.stat().st_size > 0


def test_is_unsafe_project_scan_root_home_and_fs(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert is_unsafe_project_scan_root(home) is True
    assert is_unsafe_project_scan_root("/") is True
    assert is_unsafe_project_scan_root(tmp_path / "Develop") is False


def test_profile_workspace_cwd_uses_profile_root(tmp_path, monkeypatch) -> None:
    ws = tmp_path / "Develop"
    ws.mkdir()

    class FakeMgr:
        def load_profile(self, name: str):
            return SimpleNamespace(workspace_root=str(ws))

    monkeypatch.setattr("core.profile.ProfileManager", FakeMgr)
    assert profile_workspace_cwd("admin") == str(ws.resolve())


def test_profile_workspace_cwd_rejects_home(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    class FakeMgr:
        def load_profile(self, name: str):
            return SimpleNamespace(workspace_root=str(home))

    monkeypatch.setattr("core.profile.ProfileManager", FakeMgr)
    assert profile_workspace_cwd("admin") is None
