"""Gateway request scoping for workspace path visibility."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from core.security.permissions import PermissionChecker
from core.workspace import agent_path_visibility_context


@contextmanager
def gateway_agent_path_visibility(agent: Any, key_info: dict):
    """Apply path redaction rules for the current gateway API caller."""
    checker = PermissionChecker(key_info.get("permissions") or [])
    cfg = getattr(agent, "config", None)
    with agent_path_visibility_context(
        is_admin=checker.is_admin(),
        workspace_jail_enabled=bool(getattr(cfg, "workspace_jail_enabled", False)),
    ):
        yield


@contextmanager
def gateway_agent_path_visibility_for_admin(
    agent: Any,
    *,
    is_admin: bool,
):
    """Apply path redaction when only the admin flag is known (background runs)."""
    cfg = getattr(agent, "config", None)
    with agent_path_visibility_context(
        is_admin=is_admin,
        workspace_jail_enabled=bool(getattr(cfg, "workspace_jail_enabled", False)),
    ):
        yield