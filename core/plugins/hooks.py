"""Runtime hook registries so core never statically imports outer packages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

TelegramShouldStart = Callable[[str], bool]
TelegramRunner = Callable[[str], Awaitable[None]]
MaxShouldPoll = Callable[[str], bool]
MaxRunner = Callable[[str], Awaitable[None]]
TelegramNotify = Callable[..., Awaitable[bool]]
TelegramDocumentNotify = Callable[..., Awaitable[bool]]
ListTelegramAdmins = Callable[[str], list[Any]]
MaxNotify = Callable[..., Awaitable[bool]]
SkillNoticeHook = Callable[[dict[str, Any]], Any]
ListTelegramUsers = Callable[[str], list[tuple[str, int]]]
NotifyProfileDeleted = Callable[[str, int, str], None]
RemoveTelegramBindings = Callable[[str], int]
FormatDeleteMessage = Callable[[str], str]
DescribeImageFromUrl = Callable[..., Awaitable[str]]
OpenStudioCronSession = Callable[[Any, str], str | None]
ExtraToolRegistrar = Callable[[Any], None]
WorkspaceWritten = Callable[[str, Any], None]
ProfileCredentials = Callable[[str], str | None]
WorkspaceOptions = Callable[[], dict[str, Any]]
PinConversationWorkspace = Callable[..., dict[str, Any]]
SkillNoticeTargets = Callable[[str, str], list[tuple[str, int]]]


@dataclass
class CompanionHooks:
    telegram_should_start: TelegramShouldStart | None = None
    start_telegram: TelegramRunner | None = None
    max_should_poll: MaxShouldPoll | None = None
    start_max: MaxRunner | None = None


@dataclass
class NotifyHooks:
    send_telegram: TelegramNotify | None = None
    send_telegram_document: TelegramDocumentNotify | None = None
    list_telegram_admins: ListTelegramAdmins | None = None
    send_max: MaxNotify | None = None
    skill_notice_listeners: list[SkillNoticeHook] = field(default_factory=list)


@dataclass
class ProfileLifecycleHooks:
    find_telegram_users: ListTelegramUsers | None = None
    notify_deletion_sync: NotifyProfileDeleted | None = None
    remove_bindings: RemoveTelegramBindings | None = None
    format_deletion_message: FormatDeleteMessage | None = None
    default_admin_profile: str = "admin"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class VisionHooks:
    """Gateway image descriptions. The implementation stays in integrations."""

    describe_image_from_url: DescribeImageFromUrl | None = None


@dataclass
class StudioCronHooks:
    """Write a cron run into Studio chat files. Registered at process start."""

    open_session: OpenStudioCronSession | None = None


@dataclass
class HostBridgeHooks:
    """Optional product callbacks. Empty unless that product registers them.

    The agent never imports Studio. Studio fills these when its own server starts.
    """

    register_tools: list[ExtraToolRegistrar] = field(default_factory=list)
    after_workspace_write: list[WorkspaceWritten] = field(default_factory=list)
    ensure_profile_credentials: ProfileCredentials | None = None
    workspace_options: WorkspaceOptions | None = None
    pin_conversation_workspace: PinConversationWorkspace | None = None
    skill_notice_targets: list[SkillNoticeTargets] = field(default_factory=list)


companion_hooks = CompanionHooks()
notify_hooks = NotifyHooks()
profile_lifecycle_hooks = ProfileLifecycleHooks()
vision_hooks = VisionHooks()
studio_cron_hooks = StudioCronHooks()
host_bridge_hooks = HostBridgeHooks()


def register_companion_hooks(**kwargs: Any) -> None:
    for key, value in kwargs.items():
        if hasattr(companion_hooks, key):
            setattr(companion_hooks, key, value)


def register_notify_hooks(**kwargs: Any) -> None:
    for key, value in kwargs.items():
        if key == "skill_notice_listeners":
            continue
        if hasattr(notify_hooks, key):
            setattr(notify_hooks, key, value)


def register_skill_notice_listener(fn: SkillNoticeHook) -> None:
    listeners = notify_hooks.skill_notice_listeners
    if fn not in listeners:
        listeners.append(fn)


def register_profile_lifecycle_hooks(**kwargs: Any) -> None:
    for key, value in kwargs.items():
        if hasattr(profile_lifecycle_hooks, key):
            setattr(profile_lifecycle_hooks, key, value)


def register_vision_hooks(**kwargs: Any) -> None:
    for key, value in kwargs.items():
        if hasattr(vision_hooks, key):
            setattr(vision_hooks, key, value)


def register_studio_cron_hooks(**kwargs: Any) -> None:
    for key, value in kwargs.items():
        if hasattr(studio_cron_hooks, key):
            setattr(studio_cron_hooks, key, value)


def register_host_bridge_hooks(**kwargs: Any) -> None:
    """Set scalar callbacks. List fields are appended, not replaced."""
    for key, value in kwargs.items():
        current = getattr(host_bridge_hooks, key, None)
        if isinstance(current, list):
            if value not in current:
                current.append(value)
            continue
        if hasattr(host_bridge_hooks, key):
            setattr(host_bridge_hooks, key, value)
