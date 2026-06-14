"""Telegram access requests — users apply via /start, admins approve in Telegram or CLI."""

from __future__ import annotations

from integrations.messenger.access_requests import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    MessengerAccessRequest,
)
from integrations.messenger.access_requests import (
    access_requests_path as _access_requests_path,
)
from integrations.messenger.access_requests import (
    delete_access_request as _delete_access_request,
)
from integrations.messenger.access_requests import (
    get_access_request as _get_access_request,
)
from integrations.messenger.access_requests import (
    list_pending_requests as _list_pending_requests,
)
from integrations.messenger.access_requests import (
    load_access_requests as _load_access_requests,
)
from integrations.messenger.access_requests import (
    register_access_request as _register_access_request,
)
from integrations.messenger.access_requests import (
    reject_access_request as _reject_access_request,
)
from integrations.messenger.access_requests import (
    resolve_access_request as _resolve_access_request,
)
from integrations.messenger.platforms import TELEGRAM_PLATFORM

_PLATFORM = TELEGRAM_PLATFORM
ACCESS_REQUESTS_FILE = _PLATFORM.access_requests_filename
TelegramAccessRequest = MessengerAccessRequest

__all__ = [
    "ACCESS_REQUESTS_FILE",
    "TelegramAccessRequest",
    "STATUS_APPROVED",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "access_requests_path",
    "get_access_request",
    "list_pending_requests",
    "load_access_requests",
    "register_access_request",
    "delete_access_request",
    "reject_access_request",
    "resolve_access_request",
]


def access_requests_path(bot_profile: str):
    return _access_requests_path(_PLATFORM, bot_profile)


def load_access_requests(bot_profile: str) -> dict[int, TelegramAccessRequest]:
    return _load_access_requests(_PLATFORM, bot_profile)


def list_pending_requests(bot_profile: str) -> list[TelegramAccessRequest]:
    return _list_pending_requests(_PLATFORM, bot_profile)


def get_access_request(bot_profile: str, user_id: int) -> TelegramAccessRequest | None:
    return _get_access_request(_PLATFORM, bot_profile, user_id)


def register_access_request(
    bot_profile: str,
    *,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> tuple[TelegramAccessRequest, bool]:
    return _register_access_request(
        _PLATFORM,
        bot_profile,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )


def resolve_access_request(
    bot_profile: str,
    user_id: int,
    *,
    status: str,
    holix_profile: str | None = None,
) -> TelegramAccessRequest | None:
    return _resolve_access_request(
        _PLATFORM,
        bot_profile,
        user_id,
        status=status,
        holix_profile=holix_profile,
    )


def reject_access_request(bot_profile: str, user_id: int) -> TelegramAccessRequest | None:
    return _reject_access_request(_PLATFORM, bot_profile, user_id)


def delete_access_request(bot_profile: str, user_id: int) -> bool:
    return _delete_access_request(_PLATFORM, bot_profile, user_id)