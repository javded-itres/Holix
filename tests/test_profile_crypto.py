"""Tests for profile encryption primitives."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.crypto.encrypted_fs import (
    ENCRYPTION_MAGIC,
    decrypt_bytes,
    encrypt_bytes,
    is_encrypted_file,
    read_encrypted_text,
    write_encrypted_text,
)
from core.crypto.profile_crypto import (
    ProfileCryptoError,
    create_profile_crypto,
    is_profile_encryption_enabled,
    load_crypto_meta,
    unlock_profile_dek,
    verify_unlock_key,
)
from core.crypto.unlock_context import (
    clear_profile_session_unlock,
    get_profile_session_dek,
    profile_unlock_scope,
    require_profile_dek,
    reset_profile_unlock_scope,
    set_profile_session_unlock,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_create_and_unlock_dek(holix_home, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    profile = "alice"
    pdir = holix_home / "profiles" / profile
    pdir.mkdir(parents=True)

    create_profile_crypto(profile, "test-unlock-key-123")
    assert is_profile_encryption_enabled(profile)
    meta = load_crypto_meta(profile)
    assert meta is not None
    assert meta.algorithm == "aes-256-gcm"

    dek = unlock_profile_dek(profile, "test-unlock-key-123")
    assert len(dek) == 32
    assert verify_unlock_key(profile, "test-unlock-key-123")
    assert not verify_unlock_key(profile, "wrong-key")


def test_wrong_unlock_key_raises(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    profile = "bob"
    (holix_home / "profiles" / profile).mkdir(parents=True)
    create_profile_crypto(profile, "correct-key-12345")

    with pytest.raises(ProfileCryptoError):
        unlock_profile_dek(profile, "wrong-key-12345")


def test_encrypted_fs_round_trip(tmp_path) -> None:
    dek = b"a" * 32
    plaintext = b"hello encrypted world"
    payload = encrypt_bytes(dek, plaintext)
    assert payload.startswith(ENCRYPTION_MAGIC)
    assert decrypt_bytes(dek, payload) == plaintext

    target = tmp_path / "secret.txt"
    write_encrypted_text(target, dek, "line one\nline two")
    assert is_encrypted_file(target)
    assert read_encrypted_text(target, dek) == "line one\nline two"
    assert b"line one" not in target.read_bytes()


def test_unlock_context_scope(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    profile = "carol"
    (holix_home / "profiles" / profile).mkdir(parents=True)
    create_profile_crypto(profile, "unlock-key-99999")
    dek = unlock_profile_dek(profile, "unlock-key-99999")

    tokens = profile_unlock_scope(profile=profile, dek=dek)
    try:
        assert require_profile_dek(profile) == dek
    finally:
        reset_profile_unlock_scope(tokens)

    set_profile_session_unlock(profile, dek)
    assert get_profile_session_dek(profile) == dek
    clear_profile_session_unlock(profile)
    assert get_profile_session_dek(profile) is None