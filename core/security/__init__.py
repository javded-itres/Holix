"""
Holix Security — authentication, permissions, and dangerous action confirmation.
"""

from core.security.auth import APIKeyManager, RateLimiter
from core.security.confirmation import (
    ActionGuard,
    ConfirmationChoice,
    PermissionManager,
    PermissionScope,
    RiskAssessment,
    RiskClassifier,
    RiskLevel,
    get_action_guard,
    init_action_guard,
    permission_manager,
)
from core.security.confirmation_events import (
    ConfirmationEventType,
    ConfirmationRequestEvent,
    ConfirmationResponseEvent,
)
from core.security.permissions import Permission, PermissionChecker
from core.security.safety import CommandWhitelist, ConfirmationRequired

__all__ = [
    "APIKeyManager",
    "ActionGuard",
    "CommandWhitelist",
    "ConfirmationChoice",
    "ConfirmationEventType",
    "ConfirmationRequestEvent",
    "ConfirmationRequired",
    "ConfirmationResponseEvent",
    "Permission",
    "PermissionChecker",
    "PermissionManager",
    "PermissionScope",
    "RateLimiter",
    "RiskAssessment",
    "RiskClassifier",
    "RiskLevel",
    "get_action_guard",
    "init_action_guard",
    "permission_manager",
]