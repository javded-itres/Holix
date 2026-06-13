"""Profile encryption primitives and unlock context."""

from core.crypto.encrypted_fs import (
    ENCRYPTION_MAGIC,
    decrypt_bytes,
    encrypt_bytes,
    is_encrypted_file,
    read_encrypted_text,
    write_encrypted_text,
)
from core.crypto.policy import (
    encryption_policy_status,
    is_encryption_runtime_active,
    resolve_encryption_mode,
)
from core.crypto.profile_crypto import (
    ProfileCryptoError,
    ProfileCryptoLockedError,
    ProfileCryptoMeta,
    create_profile_crypto,
    crypto_meta_path,
    is_profile_encryption_enabled,
    load_crypto_meta,
    profile_has_crypto_metadata,
    unlock_profile_dek,
)
from core.crypto.unlock_context import (
    clear_profile_session_unlock,
    clear_profile_unlock,
    get_profile_dek,
    get_profile_session_dek,
    is_profile_unlocked,
    profile_unlock_scope,
    require_profile_dek,
    reset_profile_unlock_scope,
    set_profile_session_unlock,
)

__all__ = [
    "ENCRYPTION_MAGIC",
    "ProfileCryptoError",
    "ProfileCryptoLockedError",
    "ProfileCryptoMeta",
    "clear_profile_unlock",
    "clear_profile_session_unlock",
    "create_profile_crypto",
    "crypto_meta_path",
    "decrypt_bytes",
    "encrypt_bytes",
    "get_profile_dek",
    "get_profile_session_dek",
    "encryption_policy_status",
    "is_encrypted_file",
    "is_encryption_runtime_active",
    "is_profile_encryption_enabled",
    "is_profile_unlocked",
    "profile_has_crypto_metadata",
    "resolve_encryption_mode",
    "load_crypto_meta",
    "profile_unlock_scope",
    "read_encrypted_text",
    "reset_profile_unlock_scope",
    "require_profile_dek",
    "set_profile_session_unlock",
    "unlock_profile_dek",
    "write_encrypted_text",
]