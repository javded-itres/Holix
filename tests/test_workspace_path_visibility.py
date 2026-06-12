"""Workspace-relative path display for jailed non-admin users."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core.agent_events import FinalResponseEvent, ToolCallStartEvent
from core.tools.execution_context import (
    paths_visibility_scope,
    reset_paths_visibility_scope,
    reset_workspace_scope,
    workspace_scope,
)
from core.tools.file_ops import ListDirectoryTool, ReadFileTool, WriteFileTool
from core.workspace import (
    WorkspaceJailError,
    display_path_for_user,
    resolve_tool_path,
    sanitize_agent_event,
    sanitize_paths_in_text,
)


@pytest.fixture
def jail_env(tmp_path: Path):
    jail_root = tmp_path / "workspace"
    jail_root.mkdir()
    (jail_root / "docs").mkdir()
    (jail_root / "docs" / "readme.txt").write_text("hello", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    ws_tokens = workspace_scope(workspace_root=str(jail_root), workspace_jail_enabled=True)
    vis_token = paths_visibility_scope(full_paths_visible=False)
    try:
        yield jail_root, outside
    finally:
        reset_paths_visibility_scope(vis_token)
        reset_workspace_scope(ws_tokens)


@pytest.fixture
def admin_jail_env(tmp_path: Path):
    jail_root = tmp_path / "workspace"
    jail_root.mkdir()
    file_path = jail_root / "report.txt"
    file_path.write_text("data", encoding="utf-8")

    ws_tokens = workspace_scope(workspace_root=str(jail_root), workspace_jail_enabled=True)
    vis_token = paths_visibility_scope(full_paths_visible=True)
    try:
        yield jail_root, file_path
    finally:
        reset_paths_visibility_scope(vis_token)
        reset_workspace_scope(ws_tokens)


def test_display_path_for_user_is_relative_in_jail(jail_env) -> None:
    jail_root, _ = jail_env
    target = jail_root / "docs" / "readme.txt"
    assert display_path_for_user(target) == "docs/readme.txt"


def test_display_path_for_user_keeps_full_path_for_admin(admin_jail_env) -> None:
    _, file_path = admin_jail_env
    assert display_path_for_user(file_path) == str(file_path.resolve())


def test_workspace_jail_error_hides_absolute_paths(jail_env) -> None:
    _, outside = jail_env
    with pytest.raises(WorkspaceJailError) as exc:
        resolve_tool_path(str(outside))
    message = str(exc.value)
    assert str(outside) not in message
    assert "outside.txt" in message
    assert "[restricted]" not in message


def test_sanitize_paths_in_text_replaces_workspace_prefix(jail_env) -> None:
    jail_root, _ = jail_env
    full = f"Saved to {jail_root / 'docs' / 'readme.txt'}"
    cleaned = sanitize_paths_in_text(full)
    assert str(jail_root) not in cleaned
    assert "docs/readme.txt" in cleaned


def test_sanitize_paths_in_text_hides_parent_directories(jail_env) -> None:
    jail_root, _ = jail_env
    parent = jail_root.parent
    cleaned = sanitize_paths_in_text(f"Profile data lives in {parent}")
    assert str(parent) not in cleaned
    assert "[restricted]" in cleaned


@pytest.mark.asyncio
async def test_read_file_tool_returns_relative_path(jail_env) -> None:
    jail_root, _ = jail_env
    result = await ReadFileTool().execute(str(jail_root / "docs" / "readme.txt"))
    assert str(jail_root) not in result
    assert "Content of docs/readme.txt:" in result


@pytest.mark.asyncio
async def test_write_file_tool_returns_relative_path(jail_env) -> None:
    jail_root, _ = jail_env
    result = await WriteFileTool().execute("notes.txt", "demo")
    assert str(jail_root) not in result
    assert "notes.txt" in result
    assert (jail_root / "notes.txt").is_file()


@pytest.mark.asyncio
async def test_list_directory_tool_returns_relative_path(jail_env) -> None:
    jail_root, _ = jail_env
    result = await ListDirectoryTool().execute(".")
    assert str(jail_root) not in result
    assert "Contents of .:" in result
    assert "docs" in result


def test_sanitize_agent_event_redacts_tool_arguments(jail_env) -> None:
    jail_root, _ = jail_env
    event = ToolCallStartEvent(
        tool_name="read_file",
        arguments={"path": str(jail_root / "docs" / "readme.txt")},
        arguments_raw=json.dumps({"path": str(jail_root / "docs" / "readme.txt")}),
    )
    cleaned = sanitize_agent_event(event)
    assert isinstance(cleaned, ToolCallStartEvent)
    assert cleaned.arguments["path"] == "docs/readme.txt"
    assert str(jail_root) not in cleaned.arguments_raw


def test_sanitize_agent_event_keeps_admin_paths(admin_jail_env) -> None:
    _, file_path = admin_jail_env
    text = f"File is at {file_path}"
    event = FinalResponseEvent(content=text)
    cleaned = sanitize_agent_event(event)
    assert isinstance(cleaned, FinalResponseEvent)
    assert str(file_path.resolve()) in cleaned.content