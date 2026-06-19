"""Messenger access requests — users apply via /start, admins approve in messenger or CLI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.env_loader import profile_dir_path
from core.profile.names import validate_profile_name

from integrations.messenger.platform import MessengerPlatform

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


@dataclass
class MessengerAccessRequest:
    user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    status: str = STATUS_PENDING
    requested_at: str = ""
    resolved_at: str | None = None
    holix_profile: str | None = None

    @property
    def display_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        if self.username:
            handle = f"@{self.username}"
            return f"{name} ({handle})" if name else handle
        return name or str(self.user_id)


def access_requests_path(platform: MessengerPlatform, bot_profile: str) -> Path:
    return profile_dir_path(validate_profile_name(bot_profile)) / platform.access_requests_filename


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _load_raw(platform: MessengerPlatform, bot_profile: str) -> dict[str, dict[str, Any]]:
    path = access_requests_path(platform, bot_profile)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, val in data.items():
        if isinstance(val, dict):
            out[str(key)] = val
    return out


def _save_raw(
    platform: MessengerPlatform,
    bot_profile: str,
    data: dict[str, dict[str, Any]],
) -> Path:
    path = access_requests_path(platform, bot_profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _from_dict(payload: dict[str, Any]) -> MessengerAccessRequest | None:
    uid = payload.get("user_id")
    if not isinstance(uid, int):
        uid_s = str(payload.get("user_id", "")).strip()
        if not uid_s.isdigit():
            return None
        uid = int(uid_s)
    return MessengerAccessRequest(
        user_id=int(uid),
        username=payload.get("username") or None,
        first_name=payload.get("first_name") or None,
        last_name=payload.get("last_name") or None,
        status=str(payload.get("status") or STATUS_PENDING),
        requested_at=str(payload.get("requested_at") or ""),
        resolved_at=payload.get("resolved_at"),
        holix_profile=payload.get("holix_profile"),
    )


def load_access_requests(
    platform: MessengerPlatform,
    bot_profile: str,
) -> dict[int, MessengerAccessRequest]:
    out: dict[int, MessengerAccessRequest] = {}
    for key, val in _load_raw(platform, bot_profile).items():
        if not isinstance(val, dict):
            continue
        req = _from_dict(val)
        if req is not None:
            out[req.user_id] = req
        elif key.isdigit():
            req = _from_dict({"user_id": int(key), **val})
            if req is not None:
                out[req.user_id] = req
    return out


def list_pending_requests(
    platform: MessengerPlatform,
    bot_profile: str,
) -> list[MessengerAccessRequest]:
    return sorted(
        (
            r
            for r in load_access_requests(platform, bot_profile).values()
            if r.status == STATUS_PENDING
        ),
        key=lambda r: r.requested_at or "",
    )


def get_access_request(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
) -> MessengerAccessRequest | None:
    return load_access_requests(platform, bot_profile).get(int(user_id))


def register_access_request(
    platform: MessengerPlatform,
    bot_profile: str,
    *,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> tuple[MessengerAccessRequest, bool]:
    data = _load_raw(platform, bot_profile)
    key = str(int(user_id))
    existing = _from_dict(data.get(key, {})) if key in data else None

    if existing and existing.status == STATUS_APPROVED:
        return existing, False

    now = _utc_now()
    if existing and existing.status == STATUS_PENDING:
        existing.username = username or existing.username
        existing.first_name = first_name or existing.first_name
        existing.last_name = last_name or existing.last_name
        data[key] = asdict(existing)
        _save_raw(platform, bot_profile, data)
        return existing, False

    req = MessengerAccessRequest(
        user_id=int(user_id),
        username=username,
        first_name=first_name,
        last_name=last_name,
        status=STATUS_PENDING,
        requested_at=now,
    )
    data[key] = asdict(req)
    _save_raw(platform, bot_profile, data)
    return req, True


def resolve_access_request(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
    *,
    status: str,
    holix_profile: str | None = None,
) -> MessengerAccessRequest | None:
    data = _load_raw(platform, bot_profile)
    key = str(int(user_id))
    existing = _from_dict(data.get(key, {})) if key in data else None
    if existing is None:
        return None
    existing.status = status
    existing.resolved_at = _utc_now()
    if holix_profile:
        existing.holix_profile = holix_profile.strip()
    data[key] = asdict(existing)
    _save_raw(platform, bot_profile, data)
    return existing


def reject_access_request(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
) -> MessengerAccessRequest | None:
    req = get_access_request(platform, bot_profile, user_id)
    if req is None or req.status != STATUS_PENDING:
        return None
    return resolve_access_request(
        platform,
        bot_profile,
        user_id,
        status=STATUS_REJECTED,
    )


def delete_access_request(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
) -> bool:
    """Remove access-request record so the user can apply again via /start."""
    data = _load_raw(platform, bot_profile)
    key = str(int(user_id))
    if key not in data:
        return False
    del data[key]
    if data:
        _save_raw(platform, bot_profile, data)
    else:
        path = access_requests_path(platform, bot_profile)
        if path.is_file():
            path.unlink()
    return True