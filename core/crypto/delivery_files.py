"""Materialize plaintext copies of encrypted files for user delivery."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from core.crypto.encrypted_fs import decrypt_bytes, is_encrypted_file
from core.crypto.profile_crypto import ProfileCryptoLockedError
from core.crypto.profile_files import _profile_for_path
from core.crypto.unlock_context import get_profile_session_dek, require_profile_dek


def materialize_file_for_delivery(
    path: Path,
    *,
    profile: str | None = None,
) -> tuple[Path, Callable[[], None]]:
    """Return a readable file path for outbound delivery (temp file when encrypted)."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or not is_encrypted_file(resolved):
        return resolved, lambda: None

    name = profile or _profile_for_path(resolved)
    if not name:
        return resolved, lambda: None

    dek = get_profile_session_dek(name)
    if dek is None:
        try:
            dek = require_profile_dek(name)
        except ProfileCryptoLockedError as exc:
            raise ProfileCryptoLockedError(
                f"Cannot send encrypted file '{resolved.name}': profile '{name}' is locked. "
                "Unlock the profile before sending files."
            ) from exc

    plaintext = decrypt_bytes(dek, resolved.read_bytes())
    handle = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=resolved.suffix or ".bin",
        prefix=f"holix-send-{resolved.stem[:32]}-",
    )
    try:
        handle.write(plaintext)
        handle.flush()
    finally:
        handle.close()

    temp_path = Path(handle.name)

    def _cleanup() -> None:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    return temp_path, _cleanup