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
MaxNotify = Callable[..., Awaitable[bool]]
SkillNoticeHook = Callable[[dict[str, Any]], Any]
ListTelegramUsers = Callable[[str], list[tuple[str, int]]]
NotifyProfileDeleted = Callable[[str, int, str], None]
RemoveTelegramBindings = Callable[[str], int]
FormatDeleteMessage = Callable[[str], str]


@dataclass
class CompanionHooks:
    telegram_should_start: TelegramShouldStart | None = None
    start_telegram: TelegramRunner | None = None
    max_should_poll: MaxShouldPoll | None = None
    start_max: MaxRunner | None = None


@dataclass
class NotifyHooks:
    send_telegram: TelegramNotify | None = None
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


companion_hooks = CompanionHooks()
notify_hooks = NotifyHooks()
profile_lifecycle_hooks = ProfileLifecycleHooks()


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
