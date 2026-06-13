"""Enable profile encryption (secrets + memory; workspace stays plaintext)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.crypto.memory_vault import encrypt_profile_memory, seal_profile_memory
from core.crypto.policy import profile_has_crypto_metadata
from core.crypto.profile_crypto import (
    ProfileCryptoError,
    create_profile_crypto,
    is_profile_encryption_enabled,
    unlock_profile_dek,
)
from core.crypto.profile_files import (
    decrypt_deliverable_files,
    encrypt_profile_secrets,
    seal_profile_secrets,
)
from core.crypto.unlock_context import get_profile_session_dek, set_profile_session_unlock
from core.workspace.limits import ensure_profile_limits
from core.workspace.quota import reconcile_workspace_usage


@dataclass(frozen=True, slots=True)
class EncryptionEnableResult:
    profile: str
    workspace: Path
    secrets_encrypted: int = 0
    memory_sealed: int = 0
    deliverables_decrypted: int = 0


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
        if not profile_has_crypto_metadata(name)
    ]


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
    """Enable profile encryption (crypto.json + secrets/memory; workspace stays plaintext)."""
    from core.crypto.policy import require_encryption_enable_allowed

    require_encryption_enable_allowed()
    if is_profile_encryption_enabled(profile) or profile_has_crypto_metadata(profile):
        raise ProfileCryptoError(f"Profile '{profile}' already has encryption enabled")

    workspace = _prepare_workspace_for_encryption(manager, profile)
    create_profile_crypto(profile, user_encryption_key)
    dek = unlock_profile_dek(profile, user_encryption_key)

    secrets_encrypted = 0
    memory_sealed = 0
    deliverables_decrypted = 0
    if encrypt_existing:
        deliverables_decrypted = decrypt_deliverable_files(profile, dek)
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
        secrets_encrypted=secrets_encrypted,
        memory_sealed=memory_sealed,
        deliverables_decrypted=deliverables_decrypted,
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
        if not profile_has_crypto_metadata(profile):
            summary.skipped.append(profile)
            continue
        try:
            secrets_count, deliverables_count = seal_profile_secrets(
                profile, user_encryption_key
            )
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
                    secrets_encrypted=secrets_count,
                    memory_sealed=memory_count,
                    deliverables_decrypted=deliverables_count,
                )
            )
        except (ProfileCryptoError, ValueError, OSError) as exc:
            summary.failed.append((profile, str(exc)))

    return summary


def list_encrypted_profiles(manager) -> list[str]:
    """Return profile names that have crypto.json (encryption enabled)."""
    return [
        name
        for name in manager.list_profiles()
        if profile_has_crypto_metadata(name)
    ]


def decrypt_all_profile_workspaces(
    manager,
    user_encryption_key: str,
    *,
    profiles: list[str] | None = None,
) -> MigrationSummary:
    """Decrypt legacy encrypted workspace/data/files for all encrypted profiles."""
    summary = MigrationSummary()
    targets = profiles if profiles is not None else list_encrypted_profiles(manager)

    for profile in targets:
        if not manager.profile_exists(profile):
            summary.failed.append((profile, "profile does not exist"))
            continue
        if not profile_has_crypto_metadata(profile):
            summary.skipped.append(profile)
            continue
        try:
            dek = unlock_profile_dek(profile, user_encryption_key)
            count = decrypt_deliverable_files(profile, dek)
            config = manager.load_profile(profile)
            if config.workspace_root and str(config.workspace_root).strip():
                workspace = Path(config.workspace_root).expanduser().resolve()
            else:
                workspace = manager.get_profile_dir(profile) / "workspace"
            reconcile_workspace_usage(workspace)
            summary.migrated.append(
                EncryptionEnableResult(
                    profile=profile,
                    workspace=workspace,
                    deliverables_decrypted=count,
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
        if profile_has_crypto_metadata(profile):
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