"""Profile access keys — gate switching into protected profiles."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.platform_compat import resolve_helix_home

PROFILE_KEY_FILENAME = "profile.key"
_KEY_PREFIX = "hp_"


class ProfileKeyError(Exception):
    """Raised when profile access key is missing or invalid."""


class ProfileNotFoundError(Exception):
    """Raised when the requested profile does not exist."""


class ProfileExistsError(Exception):
    """Raised when creating a profile that already exists."""


@dataclass(frozen=True)
class ProfileKeyRecord:
    version: int
    salt: str
    key_hash: str
    created_at: str


def profiles_root() -> Path:
    return resolve_helix_home() / "profiles"


def profile_dir(profile: str) -> Path:
    return profiles_root() / profile


def profile_key_path(profile: str) -> Path:
    return profile_dir(profile) / PROFILE_KEY_FILENAME


def generate_profile_access_key() -> str:
    return f"{_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def _hash_key(key: str, salt: str) -> str:
    payload = f"{salt}:{key}".encode()
    return hashlib.sha256(payload).hexdigest()


def _load_record(path: Path) -> ProfileKeyRecord | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    salt = str(data.get("salt") or "").strip()
    key_hash = str(data.get("key_hash") or "").strip()
    if not salt or not key_hash:
        return None
    return ProfileKeyRecord(
        version=int(data.get("version") or 1),
        salt=salt,
        key_hash=key_hash,
        created_at=str(data.get("created_at") or ""),
    )


def _save_record(path: Path, record: ProfileKeyRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": record.version,
        "salt": record.salt,
        "key_hash": record.key_hash,
        "created_at": record.created_at,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def profile_has_access_key(profile: str) -> bool:
    return _load_record(profile_key_path(profile)) is not None


def store_profile_access_key(profile: str, *, key: str | None = None) -> str:
    """Persist a new access key hash and return the plaintext key (show once)."""
    access_key = key or generate_profile_access_key()
    salt = secrets.token_hex(16)
    record = ProfileKeyRecord(
        version=1,
        salt=salt,
        key_hash=_hash_key(access_key, salt),
        created_at=datetime.now(UTC).isoformat(),
    )
    _save_record(profile_key_path(profile), record)
    return access_key


def verify_profile_access_key(profile: str, key: str) -> bool:
    record = _load_record(profile_key_path(profile))
    if record is None:
        return True
    if not key or not str(key).strip():
        return False
    candidate = _hash_key(str(key).strip(), record.salt)
    return secrets.compare_digest(candidate, record.key_hash)


def remove_profile_access_key(profile: str) -> bool:
    """Remove profile access key file. Returns True if a key was removed."""
    path = profile_key_path(profile)
    if not path.is_file():
        return False
    path.unlink()
    return True


def require_profile_access_key(profile: str, key: str | None) -> None:
    if not profile_has_access_key(profile):
        return
    if verify_profile_access_key(profile, key or ""):
        return
    raise ProfileKeyError(
        f"Profile '{profile}' requires an access key. "
        "Use --profile-key, HELIX_PROFILE_KEY, or helix profile key init."
    )