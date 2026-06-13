"""Tests for decrypting agent deliverables and outbound delivery."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileManager
from core.crypto.bootstrap import enable_profile_encryption, seal_profiles_secrets
from core.crypto.delivery_files import materialize_file_for_delivery
from core.crypto.encrypted_fs import encrypt_bytes, is_encrypted_file
from core.crypto.profile_crypto import (
    ProfileCryptoLockedError,
    create_profile_crypto,
    unlock_profile_dek,
)
from core.crypto.profile_files import decrypt_deliverable_files
from core.crypto.unlock_context import (
    profile_unlock_scope,
    reset_profile_unlock_scope,
    set_profile_session_unlock,
)
from core.tools.execution_context import profile_scope, reset_profile_scope


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_decrypt_deliverable_files_restores_workspace_plaintext(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("dave", inherit_global=False)
    pdir = manager.get_profile_dir("dave")
    workspace = pdir / "workspace"
    workspace.mkdir(parents=True)
    artifact = workspace / "report.txt"
    artifact.write_text("agent output", encoding="utf-8")

    key = "unlock-key-dave-del"
    enable_profile_encryption(manager, "dave", key, encrypt_existing=False)
    dek = unlock_profile_dek("dave", key)
    artifact.write_bytes(encrypt_bytes(dek, b"agent output"))
    assert is_encrypted_file(artifact)

    count = decrypt_deliverable_files("dave", dek)
    assert count == 1
    assert not is_encrypted_file(artifact)
    assert artifact.read_text(encoding="utf-8") == "agent output"


def test_materialize_file_for_delivery_decrypts_encrypted_file(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    profile = "eve"
    pdir = holix_home / "profiles" / profile
    workspace = pdir / "workspace"
    workspace.mkdir(parents=True)
    target = workspace / "notes.md"
    target.write_text("# Notes\nHello\n", encoding="utf-8")

    create_profile_crypto(profile, "unlock-key-eve-77")
    dek = unlock_profile_dek(profile, "unlock-key-eve-77")
    target.write_bytes(encrypt_bytes(dek, b"# Notes\nHello\n"))
    assert is_encrypted_file(target)

    profile_token = profile_scope(profile)
    unlock_tokens = profile_unlock_scope(profile=profile, dek=dek)
    try:
        send_path, cleanup = materialize_file_for_delivery(target, profile=profile)
        try:
            assert send_path != target
            assert send_path.read_text(encoding="utf-8") == "# Notes\nHello\n"
            assert not is_encrypted_file(send_path)
        finally:
            cleanup()
        assert not send_path.exists()
    finally:
        reset_profile_scope(profile_token)
        reset_profile_unlock_scope(unlock_tokens)


def test_materialize_file_for_delivery_returns_plaintext_path(holix_home) -> None:
    profile = "frank"
    pdir = holix_home / "profiles" / profile
    workspace = pdir / "workspace"
    workspace.mkdir(parents=True)
    target = workspace / "plain.txt"
    target.write_text("plain", encoding="utf-8")

    send_path, cleanup = materialize_file_for_delivery(target, profile=profile)
    try:
        assert send_path == target.resolve()
        assert send_path.read_text(encoding="utf-8") == "plain"
    finally:
        cleanup()


def test_unlock_decrypts_legacy_encrypted_workspace(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("henry", inherit_global=False)
    pdir = manager.get_profile_dir("henry")
    enable_profile_encryption(manager, "henry", "unlock-key-henry-1", encrypt_existing=False)
    workspace = pdir / "workspace"
    artifact = workspace / "app.py"
    artifact.write_text("print('ok')", encoding="utf-8")

    dek = unlock_profile_dek("henry", "unlock-key-henry-1")
    artifact.write_bytes(encrypt_bytes(dek, b"print('ok')"))
    assert is_encrypted_file(artifact)

    count = set_profile_session_unlock("henry", dek)
    assert count == 1
    assert not is_encrypted_file(artifact)
    assert artifact.read_text(encoding="utf-8") == "print('ok')"


def test_materialize_file_for_delivery_rejects_locked_encrypted_file(holix_home) -> None:
    profile = "locked-send"
    pdir = holix_home / "profiles" / profile
    workspace = pdir / "workspace"
    workspace.mkdir(parents=True)
    target = workspace / "out.pdf"
    target.write_text("pdf", encoding="utf-8")

    create_profile_crypto(profile, "unlock-key-locked-send")
    dek = unlock_profile_dek(profile, "unlock-key-locked-send")
    target.write_bytes(encrypt_bytes(dek, b"pdf"))

    with pytest.raises(ProfileCryptoLockedError, match="locked"):
        materialize_file_for_delivery(target, profile=profile)


def test_seal_decrypts_legacy_encrypted_workspace(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("grace", inherit_global=False)
    pdir = manager.get_profile_dir("grace")
    enable_profile_encryption(manager, "grace", "unlock-key-grace-1", encrypt_existing=False)
    workspace = pdir / "workspace"
    artifact = workspace / "legacy.py"
    artifact.write_text("print('ok')", encoding="utf-8")

    dek = unlock_profile_dek("grace", "unlock-key-grace-1")
    artifact.write_bytes(encrypt_bytes(dek, b"print('ok')"))

    summary = seal_profiles_secrets(manager, "unlock-key-grace-1", profiles=["grace"])
    assert summary.migrated[0].deliverables_decrypted == 1
    assert artifact.read_text(encoding="utf-8") == "print('ok')"