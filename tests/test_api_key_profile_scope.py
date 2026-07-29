"""API key allowed_profiles and execute-only run creation (audit #4/#5)."""

from __future__ import annotations

import pytest
from core.security.permissions import (
    PermissionChecker,
    key_allows_profile,
    parse_allowed_profiles,
)


def test_parse_allowed_profiles() -> None:
    assert parse_allowed_profiles(None) is None
    assert parse_allowed_profiles("*") is None
    assert parse_allowed_profiles("all") is None
    assert parse_allowed_profiles("a,b") == ["a", "b"]
    assert parse_allowed_profiles(["x", "y"]) == ["x", "y"]


def test_key_allows_profile_unrestricted() -> None:
    assert key_allows_profile({"permissions": ["read"]}, "any")
    assert key_allows_profile({"permissions": ["read"], "allowed_profiles": None}, "p")


def test_key_allows_profile_allowlist() -> None:
    info = {"permissions": ["execute"], "allowed_profiles": ["alice", "bob"]}
    assert key_allows_profile(info, "alice")
    assert not key_allows_profile(info, "eve")


def test_key_allows_profile_admin_bypass() -> None:
    info = {"permissions": ["admin"], "allowed_profiles": ["only-this"]}
    assert key_allows_profile(info, "other")


def test_key_allows_profile_bootstrap() -> None:
    info = {
        "permissions": ["read"],
        "allowed_profiles": ["x"],
        "bootstrap": True,
    }
    assert key_allows_profile(info, "anything")


def test_read_only_cannot_execute() -> None:
    assert not PermissionChecker(["read"]).can_execute()
    assert PermissionChecker(["execute"]).can_execute()


@pytest.mark.asyncio
async def test_unattended_blocks_python_terminal() -> None:
    from core.security.confirmation import _unattended_tool_block_reason

    assert _unattended_tool_block_reason("execute_python", {"code": "1"})
    assert _unattended_tool_block_reason(
        "run_terminal_command", {"command": "python3 -c 'print(1)'"}
    )
    assert _unattended_tool_block_reason(
        "run_terminal_command", {"command": "node script.js"}
    ) is not None
    assert (
        _unattended_tool_block_reason("run_terminal_command", {"command": "ls -la"})
        is None
    )
