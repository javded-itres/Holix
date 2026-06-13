"""Encrypt profile memory stores (SQLite + Chroma) at rest."""

from __future__ import annotations

import io
import logging
import shutil
import sqlite3
import tarfile
from pathlib import Path

from core.crypto.encrypted_fs import decrypt_bytes, encrypt_bytes, is_encrypted_file
from core.crypto.profile_crypto import (
    ProfileCryptoLockedError,
    is_profile_encryption_enabled,
    profile_has_crypto_metadata,
)
from core.crypto.runtime_cache import (
    harden_cache_tree,
    profile_runtime_cache_dir,
    wipe_legacy_profile_cache,
    wipe_profile_runtime_cache,
)
from core.crypto.unlock_context import get_profile_session_dek, require_profile_dek
from core.env_loader import profile_dir_path

logger = logging.getLogger(__name__)

VECTOR_SEALED_FILENAME = "vector_db.sealed"
SQLITE_MEMORY_FILENAMES = frozenset({"memory.db", "ltm.db", "checkpoints.db"})

_materialized_sqlite: dict[tuple[str, str], Path] = {}
_materialized_vector: dict[str, Path] = {}


def profile_from_memory_path(path: Path) -> str | None:
    """Extract profile name from a path under ``profiles/<name>/data``."""
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


def profile_data_dir(profile: str) -> Path:
    return (profile_dir_path(profile) / "data").resolve()


def memory_cache_root(profile: str) -> Path:
    return profile_runtime_cache_dir(profile)


def vector_sealed_path(vector_dir: Path) -> Path:
    return vector_dir.parent / VECTOR_SEALED_FILENAME


def _sqlite_rel_key(vault_path: Path, data_dir: Path) -> str:
    return vault_path.resolve().relative_to(data_dir.resolve()).as_posix()


def _dek_for_profile(profile: str) -> bytes | None:
    dek = get_profile_session_dek(profile)
    if dek is not None:
        return dek
    from core.crypto.profile_crypto import ProfileCryptoError
    from core.crypto.unlock_context import bootstrap_profile_unlock_from_env

    try:
        bootstrap_profile_unlock_from_env(profile)
    except ProfileCryptoError:
        return None
    return get_profile_session_dek(profile)


def _require_dek(profile: str) -> bytes:
    dek = _dek_for_profile(profile)
    if dek is not None:
        return dek
    try:
        return require_profile_dek(profile)
    except ProfileCryptoLockedError:
        raise ProfileCryptoLockedError(
            f"Profile '{profile}' memory is encrypted and locked. "
            "Unlock with: holix -p {name} --unlock-key <key>"
        ) from None


def _is_sqlite_memory_path(path: Path) -> bool:
    return path.name in SQLITE_MEMORY_FILENAMES


def _materialize_sqlite(vault_path: Path, profile: str, dek: bytes) -> Path:
    data_dir = profile_data_dir(profile)
    rel_key = _sqlite_rel_key(vault_path, data_dir)
    cache_key = (profile, rel_key)
    cache_root = memory_cache_root(profile)
    cache_root.mkdir(parents=True, exist_ok=True)
    harden_cache_tree(cache_root)
    cache_path = cache_root / rel_key
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_key in _materialized_sqlite and _materialized_sqlite[cache_key].exists():
        return _materialized_sqlite[cache_key]

    if is_encrypted_file(vault_path):
        plaintext = decrypt_bytes(dek, vault_path.read_bytes())
        cache_path.write_bytes(plaintext)
    elif vault_path.is_file():
        shutil.copy2(vault_path, cache_path)
    else:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(cache_path))
        conn.execute("PRAGMA user_version")
        conn.close()

    harden_cache_tree(cache_root)
    _materialized_sqlite[cache_key] = cache_path
    return cache_path


def _materialize_vector(vector_dir: Path, profile: str, dek: bytes) -> Path:
    if profile in _materialized_vector and _materialized_vector[profile].is_dir():
        return _materialized_vector[profile]

    data_dir = profile_data_dir(profile)
    try:
        rel = vector_dir.resolve().relative_to(data_dir)
    except ValueError:
        rel = Path("memory/vector_db")
    cache_root = memory_cache_root(profile)
    cache_root.mkdir(parents=True, exist_ok=True)
    harden_cache_tree(cache_root)
    cache_dir = cache_root / rel
    sealed = vector_sealed_path(vector_dir)

    if cache_dir.is_dir() and any(cache_dir.iterdir()):
        _materialized_vector[profile] = cache_dir
        return cache_dir

    if sealed.is_file() and is_encrypted_file(sealed):
        payload = decrypt_bytes(dek, sealed.read_bytes())
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            archive.extractall(path=cache_dir)
        harden_cache_tree(cache_root)
        _materialized_vector[profile] = cache_dir
        return cache_dir

    if vector_dir.is_dir():
        _materialized_vector[profile] = vector_dir
        return vector_dir

    cache_dir.mkdir(parents=True, exist_ok=True)
    harden_cache_tree(cache_root)
    _materialized_vector[profile] = cache_dir
    return cache_dir


def resolve_memory_sqlite_path(path: str | Path) -> Path:
    """Return a plaintext SQLite path, materializing from vault when needed."""
    vault_path = Path(path).expanduser().resolve()
    profile = profile_from_memory_path(vault_path)
    if not profile or not is_profile_encryption_enabled(profile):
        return vault_path
    if not _is_sqlite_memory_path(vault_path):
        return vault_path
    dek = _require_dek(profile)
    return _materialize_sqlite(vault_path, profile, dek)


def resolve_memory_vector_dir(path: str | Path) -> Path:
    """Return a plaintext Chroma directory, materializing from vault when needed."""
    vector_dir = Path(path).expanduser().resolve()
    profile = profile_from_memory_path(vector_dir)
    if not profile or not is_profile_encryption_enabled(profile):
        vector_dir.mkdir(parents=True, exist_ok=True)
        return vector_dir
    dek = _require_dek(profile)
    return _materialize_vector(vector_dir, profile, dek)


def seal_sqlite_vault(vault_path: Path, dek: bytes, *, profile: str) -> bool:
    """Encrypt one SQLite memory file; return True if sealed."""
    vault_path = vault_path.resolve()
    data_dir = profile_data_dir(profile)
    rel_key = _sqlite_rel_key(vault_path, data_dir)
    cache_key = (profile, rel_key)

    working = _materialized_sqlite.get(cache_key)
    if working is None or not working.is_file():
        if vault_path.is_file() and not is_encrypted_file(vault_path):
            working = vault_path
        else:
            return False

    plaintext = working.read_bytes()
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    vault_path.write_bytes(encrypt_bytes(dek, plaintext))
    try:
        vault_path.chmod(0o600)
    except OSError:
        pass

    if working != vault_path and working.exists():
        working.unlink()
    _materialized_sqlite.pop(cache_key, None)
    _cleanup_profile_cache_if_idle(profile)
    return True


def seal_vector_vault(vector_dir: Path, dek: bytes, *, profile: str) -> bool:
    """Tar+encrypt Chroma directory; return True if sealed."""
    vector_dir = vector_dir.resolve()
    sealed = vector_sealed_path(vector_dir)
    working = _materialized_vector.get(profile)
    if working is None or not working.is_dir():
        if vector_dir.is_dir() and any(vector_dir.iterdir()):
            working = vector_dir
        else:
            return False

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for item in working.rglob("*"):
            if item.is_file():
                archive.add(item, arcname=item.relative_to(working).as_posix())

    sealed.parent.mkdir(parents=True, exist_ok=True)
    sealed.write_bytes(encrypt_bytes(dek, buffer.getvalue()))
    try:
        sealed.chmod(0o600)
    except OSError:
        pass

    if working != vector_dir and working.is_dir():
        shutil.rmtree(working, ignore_errors=True)
    if vector_dir.is_dir():
        shutil.rmtree(vector_dir, ignore_errors=True)
    _materialized_vector.pop(profile, None)
    _cleanup_profile_cache_if_idle(profile)
    return True


def iter_profile_memory_sqlite_paths(profile: str) -> list[Path]:
    memory_dir = profile_data_dir(profile) / "memory"
    paths: list[Path] = []
    for name in sorted(SQLITE_MEMORY_FILENAMES):
        path = memory_dir / name
        if path.is_file():
            paths.append(path)
        elif (profile, f"memory/{name}") in _materialized_sqlite:
            paths.append(path)
    return paths


def iter_profile_vector_dirs(profile: str) -> list[Path]:
    memory_dir = profile_data_dir(profile) / "memory"
    vector_dir = memory_dir / "vector_db"
    sealed = vector_sealed_path(vector_dir)
    if vector_dir.is_dir() or sealed.is_file() or profile in _materialized_vector:
        return [vector_dir]
    return []


def seal_profile_memory(profile: str, dek: bytes) -> int:
    """Seal all memory stores for a profile; return count sealed."""
    count = 0
    for path in iter_profile_memory_sqlite_paths(profile):
        if seal_sqlite_vault(path, dek, profile=profile):
            count += 1
    for vector_dir in iter_profile_vector_dirs(profile):
        if seal_vector_vault(vector_dir, dek, profile=profile):
            count += 1
    _cleanup_profile_cache_if_idle(profile)
    return count


def seal_profile_memory_with_key(profile: str, user_encryption_key: str) -> int:
    from core.crypto.profile_crypto import unlock_profile_dek
    from core.crypto.unlock_context import set_profile_session_unlock

    if not profile_has_crypto_metadata(profile):
        raise ValueError(f"Profile '{profile}' is not encrypted")
    dek = unlock_profile_dek(profile, user_encryption_key)
    set_profile_session_unlock(profile, dek)
    return seal_profile_memory(profile, dek)


def encrypt_profile_memory(profile: str, dek: bytes) -> int:
    """Seal plaintext memory artifacts for a newly encrypted profile."""
    memory_dir = profile_data_dir(profile) / "memory"
    count = 0
    for name in SQLITE_MEMORY_FILENAMES:
        path = memory_dir / name
        if path.is_file() and not is_encrypted_file(path):
            if seal_sqlite_vault(path, dek, profile=profile):
                count += 1
    vector_dir = memory_dir / "vector_db"
    sealed = vector_sealed_path(vector_dir)
    if vector_dir.is_dir() and not sealed.is_file():
        if seal_vector_vault(vector_dir, dek, profile=profile):
            count += 1
    return count


def _profile_has_materialized_cache(profile: str) -> bool:
    if profile in _materialized_vector:
        return True
    return any(key[0] == profile for key in _materialized_sqlite)


def _cleanup_profile_cache_if_idle(profile: str) -> None:
    if _profile_has_materialized_cache(profile):
        return
    wipe_profile_runtime_cache(profile)
    wipe_legacy_profile_cache(profile)


def purge_profile_memory_cache(profile: str) -> int:
    """Remove on-disk runtime and legacy caches for a profile; return paths removed."""
    removed = 0
    if wipe_profile_runtime_cache(profile):
        removed += 1
    if wipe_legacy_profile_cache(profile):
        removed += 1
    keys = [key for key in _materialized_sqlite if key[0] == profile]
    for key in keys:
        _materialized_sqlite.pop(key, None)
    _materialized_vector.pop(profile, None)
    return removed


def clear_profile_memory_cache(profile: str) -> None:
    """Drop in-process materialization tracking (does not delete cache files)."""
    keys = [key for key in _materialized_sqlite if key[0] == profile]
    for key in keys:
        _materialized_sqlite.pop(key, None)
    _materialized_vector.pop(profile, None)