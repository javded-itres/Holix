from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any


class Permission(StrEnum):
    """Available permissions."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


def parse_allowed_profiles(raw: Any) -> list[str] | None:
    """Normalize allowed_profiles from DB / API.

    Returns:
        None — no restriction (all profiles).
        [] — empty allowlist (no profile, unless admin).
        list[str] — explicit allowlist.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text in {"*", "all"}:
            return None
        parts = [p.strip() for p in text.split(",") if p.strip()]
        return parts or None
    if isinstance(raw, (list, tuple, set)):
        parts = [str(p).strip() for p in raw if str(p).strip()]
        if not parts or parts == ["*"] or parts == ["all"]:
            return None
        return parts
    return None


def key_allows_profile(key_info: dict[str, Any] | None, profile: str) -> bool:
    """True if this API key may operate on *profile*.

    Admin keys always pass. Empty/missing allowlist = unrestricted (legacy).
    """
    info = key_info or {}
    perms = info.get("permissions") or []
    if isinstance(perms, str):
        perms = [p.strip() for p in perms.split(",") if p.strip()]
    checker = PermissionChecker(list(perms))
    if checker.is_admin() or info.get("bootstrap"):
        return True
    allowed = parse_allowed_profiles(info.get("allowed_profiles"))
    if allowed is None:
        return True
    return (profile or "").strip() in set(allowed)


class PermissionChecker:
    """Check permissions for operations."""

    def __init__(self, user_permissions: list[str] | Iterable[str] | str):
        """Initialize with user permissions.

        Args:
            user_permissions: List of permission strings (or comma-separated str)
        """
        if isinstance(user_permissions, str):
            parts = [p.strip() for p in user_permissions.split(",") if p.strip()]
        else:
            parts = [str(p).strip() for p in user_permissions if str(p).strip()]
        self.permissions: set[str] = set(parts)

    def has_permission(self, required: Permission) -> bool:
        """Check if user has required permission.

        Args:
            required: Required permission

        Returns:
            True if user has permission
        """
        # Admin has all permissions
        if Permission.ADMIN.value in self.permissions:
            return True

        return required.value in self.permissions

    def can_read(self) -> bool:
        """Check if user can read."""
        return self.has_permission(Permission.READ)

    def can_write(self) -> bool:
        """Check if user can write."""
        return self.has_permission(Permission.WRITE)

    def can_execute(self) -> bool:
        """Check if user can execute commands."""
        return self.has_permission(Permission.EXECUTE)

    def is_admin(self) -> bool:
        """Check if user is admin."""
        return Permission.ADMIN.value in self.permissions
