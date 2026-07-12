"""Extension permission checks — sandbox for third-party packages."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PERMISSION_NETWORK = "network"
PERMISSION_FILESYSTEM = "filesystem"
PERMISSION_TOOLS = "tools"
PERMISSION_SUBPROCESS = "subprocess"
PERMISSION_GATEWAY = "gateway"

ALL_PERMISSIONS = frozenset(
    {
        PERMISSION_NETWORK,
        PERMISSION_FILESYSTEM,
        PERMISSION_TOOLS,
        PERMISSION_SUBPROCESS,
        PERMISSION_GATEWAY,
    }
)

DEFAULT_PERMISSIONS = frozenset({PERMISSION_TOOLS})


def extension_permissions(ext: Any) -> frozenset[str]:
    raw = getattr(ext, "permissions", None) or frozenset()
    if not isinstance(raw, frozenset):
        raw = frozenset(str(p) for p in raw)
    return raw


def has_permission(ext: Any, permission: str) -> bool:
    perms = extension_permissions(ext)
    if not perms:
        return permission in DEFAULT_PERMISSIONS
    return permission in perms


def enforce_permissions(ext: Any, required: frozenset[str], *, context: str) -> bool:
    """Return True if extension has all required permissions; log warning otherwise."""
    perms = extension_permissions(ext) or DEFAULT_PERMISSIONS
    missing = required - perms
    if missing:
        name = getattr(ext, "name", type(ext).__name__)
        logger.warning(
            "extension %s missing permissions %s for %s (has %s)",
            name,
            sorted(missing),
            context,
            sorted(perms),
        )
        return False
    return True