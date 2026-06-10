from enum import StrEnum


class Permission(StrEnum):
    """Available permissions."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class PermissionChecker:
    """Check permissions for operations."""

    def __init__(self, user_permissions: list[str]):
        """Initialize with user permissions.

        Args:
            user_permissions: List of permission strings
        """
        self.permissions: set[str] = set(user_permissions)

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
