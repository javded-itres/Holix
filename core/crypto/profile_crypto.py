"""Per-profile DEK wrap/unwrap and crypto.json metadata."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.profile_keys import profile_dir

CRYPTO_FILENAME = "crypto.json"
DEK_SIZE = 32
NONCE_SIZE = 12
DEFAULT_KDF_MEMORY_KIB = 65536
DEFAULT_KDF_TIME_COST = 3
DEFAULT_KDF_PARALLELISM = 4


class ProfileCryptoError(Exception):
    """Invalid crypto configuration or wrong unlock key."""


class ProfileCryptoLockedError(ProfileCryptoError):
    """Profile data is encrypted but no DEK is loaded in this context."""


@dataclass(frozen=True, slots=True)
class ProfileCryptoMeta:
    version: int
    algorithm: str
    kdf: str
    kdf_memory_kib: int
    kdf_time_cost: int
    kdf_parallelism: int
    salt: bytes
    dek_wrap_nonce: bytes
    dek_wrapped: bytes
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "algorithm": self.algorithm,
            "kdf": self.kdf,
            "kdf_params": {
                "m": self.kdf_memory_kib,
                "t": self.kdf_time_cost,
                "p": self.kdf_parallelism,
            },
            "salt": _b64(self.salt),
            "dek_wrap_nonce": _b64(self.dek_wrap_nonce),
            "dek_wrapped": _b64(self.dek_wrapped),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileCryptoMeta:
        params = data.get("kdf_params") or {}
        return cls(
            version=int(data.get("version") or 1),
            algorithm=str(data.get("algorithm") or "aes-256-gcm"),
            kdf=str(data.get("kdf") or "argon2id"),
            kdf_memory_kib=int(params.get("m") or DEFAULT_KDF_MEMORY_KIB),
            kdf_time_cost=int(params.get("t") or DEFAULT_KDF_TIME_COST),
            kdf_parallelism=int(params.get("p") or DEFAULT_KDF_PARALLELISM),
            salt=_b64_decode(str(data.get("salt") or "")),
            dek_wrap_nonce=_b64_decode(str(data.get("dek_wrap_nonce") or "")),
            dek_wrapped=_b64_decode(str(data.get("dek_wrapped") or "")),
            created_at=str(data.get("created_at") or ""),
        )


def _b64(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64_decode(text: str) -> bytes:
    import base64

    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def crypto_meta_path(profile: str) -> Path:
    return profile_dir(profile) / CRYPTO_FILENAME


def load_crypto_meta(profile: str) -> ProfileCryptoMeta | None:
    path = crypto_meta_path(profile)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ProfileCryptoError(f"Invalid crypto metadata for profile '{profile}'") from exc
    return ProfileCryptoMeta.from_dict(data)


def save_crypto_meta(profile: str, meta: ProfileCryptoMeta) -> None:
    path = crypto_meta_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta.to_dict(), indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def is_profile_encryption_enabled(profile: str) -> bool:
    from core.crypto.policy import is_profile_encryption_enabled as _enabled

    return _enabled(profile)


def profile_has_crypto_metadata(profile: str) -> bool:
    return load_crypto_meta(profile) is not None


def derive_kek(user_encryption_key: str, meta: ProfileCryptoMeta) -> bytes:
    secret = user_encryption_key.encode("utf-8")
    return hash_secret_raw(
        secret=secret,
        salt=meta.salt,
        time_cost=meta.kdf_time_cost,
        memory_cost=meta.kdf_memory_kib,
        parallelism=meta.kdf_parallelism,
        hash_len=DEK_SIZE,
        type=Type.ID,
    )


def wrap_dek(dek: bytes, kek: bytes) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(NONCE_SIZE)
    aes = AESGCM(kek)
    wrapped = aes.encrypt(nonce, dek, None)
    return nonce, wrapped


def unwrap_dek(meta: ProfileCryptoMeta, kek: bytes) -> bytes:
    aes = AESGCM(kek)
    try:
        dek = aes.decrypt(meta.dek_wrap_nonce, meta.dek_wrapped, None)
    except Exception as exc:
        raise ProfileCryptoError("Invalid unlock key") from exc
    if len(dek) != DEK_SIZE:
        raise ProfileCryptoError("Invalid wrapped DEK")
    return dek


def create_profile_crypto(profile: str, user_encryption_key: str) -> ProfileCryptoMeta:
    uek = (user_encryption_key or "").strip()
    if len(uek) < 8:
        raise ProfileCryptoError("Unlock key must be at least 8 characters")

    salt = secrets.token_bytes(16)
    meta_stub = ProfileCryptoMeta(
        version=1,
        algorithm="aes-256-gcm",
        kdf="argon2id",
        kdf_memory_kib=DEFAULT_KDF_MEMORY_KIB,
        kdf_time_cost=DEFAULT_KDF_TIME_COST,
        kdf_parallelism=DEFAULT_KDF_PARALLELISM,
        salt=salt,
        dek_wrap_nonce=b"",
        dek_wrapped=b"",
        created_at=datetime.now(UTC).isoformat(),
    )
    kek = derive_kek(uek, meta_stub)
    dek = secrets.token_bytes(DEK_SIZE)
    nonce, wrapped = wrap_dek(dek, kek)
    meta = ProfileCryptoMeta(
        version=meta_stub.version,
        algorithm=meta_stub.algorithm,
        kdf=meta_stub.kdf,
        kdf_memory_kib=meta_stub.kdf_memory_kib,
        kdf_time_cost=meta_stub.kdf_time_cost,
        kdf_parallelism=meta_stub.kdf_parallelism,
        salt=meta_stub.salt,
        dek_wrap_nonce=nonce,
        dek_wrapped=wrapped,
        created_at=meta_stub.created_at,
    )
    save_crypto_meta(profile, meta)
    return meta


def unlock_profile_dek(profile: str, user_encryption_key: str) -> bytes:
    meta = load_crypto_meta(profile)
    if meta is None:
        raise ProfileCryptoError(f"Profile '{profile}' is not encrypted")
    kek = derive_kek(user_encryption_key.strip(), meta)
    return unwrap_dek(meta, kek)


def verify_unlock_key(profile: str, user_encryption_key: str) -> bool:
    try:
        unlock_profile_dek(profile, user_encryption_key)
        return True
    except ProfileCryptoError:
        return False