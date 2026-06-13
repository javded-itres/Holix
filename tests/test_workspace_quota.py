"""Tests for workspace quota and encrypted storage."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.crypto.encrypted_fs import encrypt_bytes, is_encrypted_file
from core.crypto.profile_crypto import create_profile_crypto, unlock_profile_dek
from core.crypto.unlock_context import profile_unlock_scope, reset_profile_unlock_scope
from core.tools.execution_context import (
    profile_scope,
    reset_profile_scope,
    reset_workspace_scope,
    workspace_scope,
)
from core.workspace.limits import (
    ProfileLimits,
    ensure_profile_limits,
    load_profile_limits,
    save_profile_limits,
)
from core.workspace.quota import (
    WorkspaceQuotaExceeded,
    check_workspace_write,
    reconcile_workspace_usage,
)
from core.workspace.storage import read_profile_file_text, write_profile_file_text


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _tool_context(profile: str, workspace_root, dek: bytes | None = None):
    ws_tokens = workspace_scope(
        workspace_root=str(workspace_root),
        workspace_jail_enabled=True,
    )
    profile_token = profile_scope(profile)
    unlock_tokens = []
    if dek is not None:
        unlock_tokens = profile_unlock_scope(profile=profile, dek=dek)
    return ws_tokens, profile_token, unlock_tokens


def _reset_tool_context(ws_tokens, profile_token, unlock_tokens) -> None:
    reset_workspace_scope(ws_tokens)
    reset_profile_scope(profile_token)
    if unlock_tokens:
        reset_profile_unlock_scope(unlock_tokens)


def test_ensure_profile_limits_default(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    profile = "quota_user"
    (holix_home / "profiles" / profile).mkdir(parents=True)

    limits = ensure_profile_limits(profile)
    assert limits.tariff_id == "free"
    assert limits.workspace_max_bytes == 100 * 1024 * 1024
    assert load_profile_limits(profile) is not None


def test_workspace_stays_plaintext_when_encryption_enabled(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    profile = "enc_ws"
    pdir = holix_home / "profiles" / profile
    workspace = pdir / "workspace"
    workspace.mkdir(parents=True)
    create_profile_crypto(profile, "unlock-key-enc-ws")
    dek = unlock_profile_dek(profile, "unlock-key-enc-ws")

    target = workspace / "main.py"
    ws_tokens, profile_token, unlock_tokens = _tool_context(profile, workspace, dek)
    try:
        write_profile_file_text(target, "def main():\n    pass\n", profile=profile)
        content = read_profile_file_text(target, profile=profile)
    finally:
        _reset_tool_context(ws_tokens, profile_token, unlock_tokens)

    assert content == "def main():\n    pass\n"
    assert not is_encrypted_file(target)
    assert b"def main" in target.read_bytes()


def test_read_decrypts_legacy_encrypted_workspace_file(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    profile = "legacy_read"
    pdir = holix_home / "profiles" / profile
    workspace = pdir / "workspace"
    workspace.mkdir(parents=True)
    create_profile_crypto(profile, "unlock-key-legacy-read")
    dek = unlock_profile_dek(profile, "unlock-key-legacy-read")

    target = workspace / "main.py"
    target.write_bytes(encrypt_bytes(dek, b"def main(): pass\n"))

    ws_tokens, profile_token, unlock_tokens = _tool_context(profile, workspace, dek)
    try:
        content = read_profile_file_text(target, profile=profile)
    finally:
        _reset_tool_context(ws_tokens, profile_token, unlock_tokens)

    assert content == "def main(): pass\n"
    assert not is_encrypted_file(target)


def test_quota_blocks_large_write(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    profile = "quota_block"
    pdir = holix_home / "profiles" / profile
    workspace = pdir / "workspace"
    workspace.mkdir(parents=True)

    save_profile_limits(
        profile,
        ProfileLimits(
            version=1,
            tariff_id="free",
            workspace_max_bytes=1024,
            workspace_max_files=10,
            source="test",
            updated_at="2026-01-01T00:00:00Z",
            updated_by="test",
        ),
    )
    reconcile_workspace_usage(workspace)

    target = workspace / "big.bin"
    ws_tokens, profile_token, _ = _tool_context(profile, workspace)
    try:
        with pytest.raises(WorkspaceQuotaExceeded):
            check_workspace_write(
                profile=profile,
                workspace_root=workspace,
                target=target,
                new_payload_bytes=2048,
            )
    finally:
        _reset_tool_context(ws_tokens, profile_token, [])