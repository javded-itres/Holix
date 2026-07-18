"""Optional outer-layer hooks (CLI/integrations) registered at process startup."""

from core.plugins.hooks import (
    CompanionHooks,
    NotifyHooks,
    ProfileLifecycleHooks,
    companion_hooks,
    notify_hooks,
    profile_lifecycle_hooks,
    register_companion_hooks,
    register_notify_hooks,
    register_profile_lifecycle_hooks,
)

__all__ = [
    "CompanionHooks",
    "NotifyHooks",
    "ProfileLifecycleHooks",
    "companion_hooks",
    "notify_hooks",
    "profile_lifecycle_hooks",
    "register_companion_hooks",
    "register_notify_hooks",
    "register_profile_lifecycle_hooks",
]
