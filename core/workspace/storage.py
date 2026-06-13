"""Workspace file I/O (plaintext) with quota enforcement."""

from __future__ import annotations

from pathlib import Path

from core.crypto.encrypted_fs import is_encrypted_file, read_encrypted_text
from core.crypto.profile_crypto import ProfileCryptoLockedError
from core.crypto.profile_files import decrypt_deliverable_file
from core.crypto.unlock_context import get_profile_session_dek, require_profile_dek
from core.workspace import get_effective_workspace_root
from core.workspace.quota import (
    WorkspaceQuotaExceeded,
    apply_workspace_write_delta,
    check_workspace_write,
)


def _workspace_root_or_none() -> Path | None:
    return get_effective_workspace_root()


def path_is_in_workspace(file_path: Path) -> bool:
    root = _workspace_root_or_none()
    if root is None:
        return False
    try:
        file_path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def should_encrypt_path(file_path: Path, profile: str) -> bool:
    """Workspace files stay plaintext (git-friendly); profile secrets use profile_files."""
    return False


def _dek_for_profile(profile: str) -> bytes | None:
    dek = get_profile_session_dek(profile)
    if dek is not None:
        return dek
    try:
        return require_profile_dek(profile)
    except ProfileCryptoLockedError:
        return None


def _ensure_workspace_plaintext(file_path: Path, *, profile: str) -> None:
    """Decrypt a legacy encrypted workspace file in place when unlock is available."""
    if not path_is_in_workspace(file_path) or not is_encrypted_file(file_path):
        return
    dek = _dek_for_profile(profile)
    if dek is not None:
        decrypt_deliverable_file(file_path, dek)


def read_profile_file_text(file_path: Path, *, profile: str, encoding: str = "utf-8") -> str:
    _ensure_workspace_plaintext(file_path, profile=profile)

    if file_path.is_file() and is_encrypted_file(file_path):
        dek = _dek_for_profile(profile)
        if dek is None:
            raise ProfileCryptoLockedError(
                f"Profile '{profile}' is encrypted and locked. "
                "Unlock before reading encrypted workspace files."
            )
        return read_encrypted_text(file_path, dek, encoding=encoding)

    return file_path.read_text(encoding=encoding)


def write_profile_file_text(
    file_path: Path,
    content: str,
    *,
    profile: str,
    encoding: str = "utf-8",
) -> int:
    """Write file as plaintext; return bytes stored on disk."""
    old_size = file_path.stat().st_size if file_path.is_file() else 0
    created = not file_path.exists()
    root = _workspace_root_or_none()

    payload = content.encode(encoding)
    if root is not None and path_is_in_workspace(file_path):
        check_workspace_write(
            profile=profile,
            workspace_root=root,
            target=file_path,
            new_payload_bytes=len(payload),
            previous_size=old_size,
        )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding=encoding)
    new_size = len(payload)

    if root is not None and path_is_in_workspace(file_path):
        apply_workspace_write_delta(
            root,
            old_size=old_size,
            new_size=file_path.stat().st_size if file_path.is_file() else new_size,
            created=created,
        )
    return new_size


def file_exists_for_profile(file_path: Path, *, profile: str) -> bool:
    return file_path.is_file()


def format_quota_error(exc: WorkspaceQuotaExceeded) -> str:
    return f"Error: {exc}"