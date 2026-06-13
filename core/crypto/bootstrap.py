"""Enable profile encryption and migrate existing workspace files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.crypto.encrypted_fs import encrypt_bytes, is_encrypted_file
from core.crypto.memory_vault import encrypt_profile_memory, seal_profile_memory
from core.crypto.profile_crypto import (
    ProfileCryptoError,
    create_profile_crypto,
    is_profile_encryption_enabled,
    unlock_profile_dek,
)
from core.crypto.profile_files import encrypt_profile_secrets, seal_profile_secrets
from core.crypto.unlock_context import get_profile_session_dek, set_profile_session_unlock
from core.workspace.limits import ensure_profile_limits
from core.workspace.quota import QUOTA_DIRNAME, reconcile_workspace_usage


@dataclass(frozen=True, slots=True)
class EncryptionEnableResult:
    profile: str
    workspace: Path
    files_encrypted: int
    secrets_encrypted: int = 0
    memory_sealed: int = 0


@dataclass(slots=True)
class MigrationSummary:
    migrated: list[EncryptionEnableResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def list_unencrypted_profiles(manager) -> list[str]:
    """Return profile names that do not have crypto.json yet."""
    return [
        name
        for name in manager.list_profiles()
        if not is_profile_encryption_enabled(name)
    ]


def encrypt_workspace_tree(workspace_root: Path, dek: bytes) -> int:
    """Encrypt plaintext files under workspace; return count of files encrypted."""
    root = workspace_root.resolve()
    if not root.is_dir():
        return 0

    count = 0
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        try:
            rel = item.relative_to(root)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == QUOTA_DIRNAME:
            continue
        if is_encrypted_file(item):
            continue
        plaintext = item.read_bytes()
        item.write_bytes(encrypt_bytes(dek, plaintext))
        count += 1
    return count


def _prepare_workspace_for_encryption(manager, profile: str) -> Path:
    """Ensure workspace jail + directory; preserve an existing jail root when set."""
    from cli.core import enable_profile_workspace_isolation

    config = manager.load_profile(profile)
    if config.workspace_jail_enabled and config.workspace_root and str(config.workspace_root).strip():
        workspace = Path(config.workspace_root).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        ensure_profile_limits(profile)
        reconcile_workspace_usage(workspace)
        return workspace

    return enable_profile_workspace_isolation(manager, profile)


def enable_profile_encryption(
    manager,
    profile: str,
    user_encryption_key: str,
    *,
    encrypt_existing: bool = True,
) -> EncryptionEnableResult:
    """Enable workspace encryption for a profile (workspace jail + crypto.json)."""
    if is_profile_encryption_enabled(profile):
        raise ProfileCryptoError(f"Profile '{profile}' already has encryption enabled")

    workspace = _prepare_workspace_for_encryption(manager, profile)
    create_profile_crypto(profile, user_encryption_key)
    dek = unlock_profile_dek(profile, user_encryption_key)

    files_encrypted = 0
    secrets_encrypted = 0
    memory_sealed = 0
    if encrypt_existing:
        files_encrypted = encrypt_workspace_tree(workspace, dek)
        secrets_encrypted = encrypt_profile_secrets(profile, dek)
        memory_sealed = encrypt_profile_memory(profile, dek)
    reconcile_workspace_usage(workspace)

    config = manager.load_profile(profile)
    config.encryption_enabled = True
    manager.save_profile(profile, config)
    set_profile_session_unlock(profile, dek)
    return EncryptionEnableResult(
        profile=profile,
        workspace=workspace,
        files_encrypted=files_encrypted,
        secrets_encrypted=secrets_encrypted,
        memory_sealed=memory_sealed,
    )


def seal_profiles_secrets(
    manager,
    user_encryption_key: str,
    *,
    profiles: list[str] | None = None,
) -> MigrationSummary:
    """Encrypt plaintext secrets and memory stores for encrypted profiles."""
    summary = MigrationSummary()
    targets = profiles if profiles is not None else manager.list_profiles()

    for profile in targets:
        if not manager.profile_exists(profile):
            summary.failed.append((profile, "profile does not exist"))
            continue
        if not is_profile_encryption_enabled(profile):
            summary.skipped.append(profile)
            continue
        try:
            secrets_count = seal_profile_secrets(profile, user_encryption_key)
            dek = get_profile_session_dek(profile)
            memory_count = seal_profile_memory(profile, dek) if dek else 0
            config = manager.load_profile(profile)
            if config.workspace_root and str(config.workspace_root).strip():
                workspace = Path(config.workspace_root).expanduser().resolve()
            else:
                workspace = manager.get_profile_dir(profile) / "workspace"
            summary.migrated.append(
                EncryptionEnableResult(
                    profile=profile,
                    workspace=workspace,
                    files_encrypted=0,
                    secrets_encrypted=secrets_count,
                    memory_sealed=memory_count,
                )
            )
        except (ProfileCryptoError, ValueError, OSError) as exc:
            summary.failed.append((profile, str(exc)))

    return summary


def migrate_profiles_encryption(
    manager,
    user_encryption_key: str,
    *,
    profiles: list[str] | None = None,
    encrypt_existing: bool = True,
) -> MigrationSummary:
    """Encrypt all (or selected) profiles that are not encrypted yet."""
    summary = MigrationSummary()
    targets = profiles if profiles is not None else manager.list_profiles()

    for profile in targets:
        if not manager.profile_exists(profile):
            summary.failed.append((profile, "profile does not exist"))
            continue
        if is_profile_encryption_enabled(profile):
            summary.skipped.append(profile)
            continue
        try:
            result = enable_profile_encryption(
                manager,
                profile,
                user_encryption_key,
                encrypt_existing=encrypt_existing,
            )
            summary.migrated.append(result)
        except ProfileCryptoError as exc:
            summary.failed.append((profile, str(exc)))
        except OSError as exc:
            summary.failed.append((profile, str(exc)))

    return summary