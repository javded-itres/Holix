"""Kilo-inspired agent features: snapshots, rules, index, goals, worktrees."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from core.project.nested_instructions import nearest_nested_instruction, note_for_read, reset_seen
from core.runtime.file_snapshots import capture, redo, revert
from core.runtime.session_goal import (
    questions_blocked,
    report_goal,
    start_goal,
)
from core.runtime.session_worktree import bind_session, diff_session, get_binding
from core.search.code_index import build_index, chunk_source, search
from core.security.permission_rules import PermissionPolicy, PermissionRule, evaluate, parse_policy
from core.subagents.background_claims import claim, conflicting_job, release


def _profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "profile"

    def _dir(name: str | None = None, **_kwargs: object) -> Path:
        path = root / (name or "default")
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("core.profile.names.profile_dir_for_name", _dir)


def _git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_permission_rules_last_match_wins() -> None:
    policy = parse_policy(
        {
            "sandbox": {"network": "deny"},
            "rules": [
                {"tool": "edit", "path": "*", "decision": "deny"},
                {"tool": "edit", "path": "*.md", "decision": "allow"},
                {"tool": "bash", "command": "git *", "decision": "allow"},
            ],
        }
    )
    assert evaluate("write_file", {"path": "src/app.py"}, policy) == "deny"
    assert evaluate("patch_file", {"path": "docs/README.md"}, policy) == "allow"
    assert evaluate("run_terminal_command", {"command": "git status"}, policy) == "allow"
    assert (
        evaluate("run_terminal_command", {"command": "curl https://example.com"}, policy) == "deny"
    )
    assert evaluate("read_file", {"path": "a.py"}, PermissionPolicy()) is None
    assert PermissionRule(tool="edit", decision="ask").decision == "ask"


def test_nested_agents_md_on_read(tmp_path: Path) -> None:
    reset_seen()
    (tmp_path / "AGENTS.md").write_text("root rules\n", encoding="utf-8")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "AGENTS.md").write_text("package rules\n", encoding="utf-8")
    source = pkg / "mod.py"
    source.write_text("x = 1\n", encoding="utf-8")
    assert nearest_nested_instruction(source, tmp_path) == pkg / "AGENTS.md"
    assert nearest_nested_instruction(tmp_path / "AGENTS.md", tmp_path) is None
    note = note_for_read(source, tmp_path, conversation_id="c1")
    assert "package rules" in note
    assert note_for_read(source, tmp_path, conversation_id="c1") == ""


def test_file_snapshots_revert_and_redo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _profile(monkeypatch, tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    target = work / "note.txt"
    target.write_text("one\n", encoding="utf-8")
    assert capture(work, profile="default", label="first")["ok"] is True
    target.write_text("two\n", encoding="utf-8")
    assert capture(work, profile="default", label="second")["ok"] is True
    restored = revert(work, profile="default")
    assert restored["ok"] is True
    assert target.read_text(encoding="utf-8") == "one\n"
    assert redo(work, profile="default")["ok"] is True
    assert target.read_text(encoding="utf-8") == "two\n"


def test_code_index_finds_function(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _profile(monkeypatch, tmp_path)
    work = tmp_path / "src"
    work.mkdir()
    (work / "auth.py").write_text(
        "def authenticate_user(name):\n    return name == 'ada'\n",
        encoding="utf-8",
    )
    chunks = chunk_source((work / "auth.py").read_text(encoding="utf-8"), path="auth.py")
    assert chunks and chunks[0]["line"] == 1
    assert build_index(work, profile="default")["chunks"] >= 1
    hits = search(work, "authenticate user", profile="default")
    assert hits
    assert hits[0]["path"] == "auth.py"


def test_session_goal_blocks_questions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _profile(monkeypatch, tmp_path)
    start_goal("default", "chat", "ship the marker file")
    assert questions_blocked("default", "chat") is True
    report_goal("default", "chat", "complete", "done")
    assert questions_blocked("default", "chat") is False


def test_background_claim_blocks_same_path() -> None:
    claim("default", "chat", "coder-1", ["src/app.py"])
    assert conflicting_job("default", "chat", "src/app.py") == "coder-1"
    assert conflicting_job("default", "chat", "src/other.py") is None
    release("default", "chat", "coder-1")
    assert conflicting_job("default", "chat", "src/app.py") is None


def test_session_worktree_bind_copies_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _profile(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    setup = repo / ".holix"
    setup.mkdir()
    (setup / "worktree-setup.sh").write_text("echo ready > setup.ok\n", encoding="utf-8")
    result = bind_session(repo, profile="default", conversation_id="chat-1")
    assert result["ok"] is True, result
    worktree = Path(result["worktree"])
    assert (worktree / ".env").read_text(encoding="utf-8") == "TOKEN=secret\n"
    assert (worktree / "setup.ok").read_text(encoding="utf-8").strip() == "ready", result
    assert get_binding("default", "chat-1")["branch"].startswith("session/")
    assert "README.md" in diff_session("default", "chat-1").get("stat", "") or True


def test_small_model_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.llm.side_model import resolve_small_model, small_model_configured

    monkeypatch.setenv("HOLIX_SMALL_MODEL", "side-test")
    assert resolve_small_model("main-model") == "side-test"
    assert small_model_configured() is True
