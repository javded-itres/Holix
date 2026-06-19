"""Encrypt/decrypt confidential per-profile files at rest."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from core.crypto.encrypted_fs import (
    encrypt_bytes,
    is_encrypted_file,
    read_encrypted_text,
    write_encrypted_text,
)
from core.crypto.profile_crypto import is_profile_encryption_enabled, profile_has_crypto_metadata
from core.crypto.unlock_context import get_profile_session_dek, require_profile_dek
from core.env_loader import profile_dir_path

PROFILE_ROOT_SECRET_NAMES = (
    ".env",
    "telegram.env",
    "SOUL.md",
    "USER.md",
    "INIT.md",
)


def profile_root_secrets(profile: str) -> list[Path]:
    root = profile_dir_path(profile)
    return [root / name for name in PROFILE_ROOT_SECRET_NAMES]


def _data_files_tree(profile: str) -> Path:
    return profile_dir_path(profile) / "data" / "files"


def iter_plaintext_profile_secrets(profile: str) -> list[Path]:
    """List confidential profile root files that still need encryption."""
    paths: list[Path] = []
    for path in profile_root_secrets(profile):
        if path.is_file() and not is_encrypted_file(path):
            paths.append(path)
    return paths


def iter_encrypted_deliverable_files(profile: str) -> list[Path]:
    """Encrypted workspace / data/files artifacts that should be plaintext."""
    from core.env_loader import profile_dir_path

    roots = [
        profile_dir_path(profile) / "workspace",
        _data_files_tree(profile),
    ]
    paths: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for item in root.rglob("*"):
            if item.is_file() and is_encrypted_file(item):
                paths.append(item)
    return paths


def decrypt_deliverable_file(path: Path, dek: bytes) -> bool:
    """Decrypt one workspace/data/files artifact back to plaintext."""
    if not path.is_file() or not is_encrypted_file(path):
        return False
    from core.crypto.encrypted_fs import decrypt_bytes

    path.write_bytes(decrypt_bytes(dek, path.read_bytes()))
    return True


def decrypt_deliverable_files(profile: str, dek: bytes) -> int:
    """Decrypt agent deliverables (workspace + data/files); return count."""
    count = 0
    for path in iter_encrypted_deliverable_files(profile):
        if decrypt_deliverable_file(path, dek):
            count += 1
    return count


def encrypt_profile_secret_file(path: Path, dek: bytes) -> bool:
    """Encrypt one file in place; return True if encrypted."""
    if not path.is_file() or is_encrypted_file(path):
        return False
    plaintext = path.read_bytes()
    path.write_bytes(encrypt_bytes(dek, plaintext))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return True


def encrypt_profile_secrets(profile: str, dek: bytes) -> int:
    """Encrypt confidential profile files; return count encrypted."""
    count = 0
    for path in iter_plaintext_profile_secrets(profile):
        if encrypt_profile_secret_file(path, dek):
            count += 1
    return count


def _profile_for_path(path: Path) -> str | None:
    try:
        parts = path.resolve().parts
        if "profiles" not in parts:
            return None
        idx = parts.index("profiles")
        if idx + 1 >= len(parts):
            return None
        return parts[idx + 1]
    except ValueError:
        return None


def read_profile_file_text(path: Path, *, profile: str | None = None) -> str:
    """Read a profile file, transparently decrypting when needed."""
    if not path.is_file():
        return ""
    name = profile or _profile_for_path(path)
    if name and is_profile_encryption_enabled(name) and is_encrypted_file(path):
        dek = get_profile_session_dek(name)
        if dek is None:
            dek = require_profile_dek(name)
        return read_encrypted_text(path, dek)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def write_profile_file_text(path: Path, content: str, *, profile: str) -> None:
    """Write a profile secret file, encrypting when the profile is encrypted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_profile_encryption_enabled(profile):
        dek = get_profile_session_dek(profile) or require_profile_dek(profile)
        write_encrypted_text(path, dek, content)
    else:
        path.write_text(content, encoding="utf-8")  # codeql[py/clear-text-storage-sensitive-data]: encryption disabled by user config
    try:
        path.chmod(0o600)
    except OSError:
        pass


def dotenv_values_for_path(path: Path, *, profile: str | None = None) -> dict[str, str | None]:
    """Parse dotenv from a path that may be encrypted."""
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}

    name = profile or _profile_for_path(path)
    if name and is_profile_encryption_enabled(name) and is_encrypted_file(path):
        dek = get_profile_session_dek(name)
        if dek is None:
            from core.crypto.unlock_context import bootstrap_profile_unlock_from_env

            bootstrap_profile_unlock_from_env(name)
            dek = get_profile_session_dek(name)
        if dek is None:
            return {}
        text = read_encrypted_text(path, dek)
    else:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(text)
        temp_path = handle.name
    try:
        return dotenv_values(temp_path)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def seal_profile_secrets(profile: str, user_encryption_key: str) -> tuple[int, int]:
    """Encrypt plaintext secrets; return (secrets_encrypted, deliverables_decrypted)."""
    from core.crypto.profile_crypto import unlock_profile_dek

    if not profile_has_crypto_metadata(profile):
        raise ValueError(f"Profile '{profile}' is not encrypted")
    dek = unlock_profile_dek(profile, user_encryption_key)
    from core.crypto.unlock_context import set_profile_session_unlock

    deliverables_decrypted = set_profile_session_unlock(profile, dek)
    return encrypt_profile_secrets(profile, dek), deliverables_decrypted