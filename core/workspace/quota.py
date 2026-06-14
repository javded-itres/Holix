"""Workspace storage quota tracking and enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.crypto.encrypted_fs import ENCRYPTION_MAGIC, is_encrypted_file
from core.profile.names import validate_profile_name
from core.workspace.limits import ProfileLimits, ensure_profile_limits, load_profile_limits

QUOTA_DIRNAME = ".holix"
QUOTA_FILENAME = "quota.json"
TMP_DIRNAME = "tmp"


class WorkspaceQuotaExceeded(Exception):
    """Raised when a write would exceed platform-managed workspace limits."""


@dataclass(frozen=True, slots=True)
class QuotaUsage:
    version: int
    used_bytes: int
    file_count: int
    last_reconciled_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "used_bytes": self.used_bytes,
            "file_count": self.file_count,
            "last_reconciled_at": self.last_reconciled_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuotaUsage:
        return cls(
            version=int(data.get("version") or 1),
            used_bytes=int(data.get("used_bytes") or 0),
            file_count=int(data.get("file_count") or 0),
            last_reconciled_at=str(data.get("last_reconciled_at") or ""),
        )


def _resolve_workspace_root(workspace_root: Path) -> Path:
    return workspace_root.expanduser().resolve()


def quota_state_path(workspace_root: Path) -> Path:
    return _resolve_workspace_root(workspace_root) / QUOTA_DIRNAME / QUOTA_FILENAME


def _is_quota_excluded(path: Path, workspace_root: Path) -> bool:
    root = _resolve_workspace_root(workspace_root)
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return True
    parts = rel.parts
    if not parts:
        return True
    if parts[0] == QUOTA_DIRNAME:
        return True
    if parts[0] == QUOTA_DIRNAME and len(parts) > 1 and parts[1] == TMP_DIRNAME:
        return True
    if QUOTA_DIRNAME in parts and TMP_DIRNAME in parts:
        idx = parts.index(QUOTA_DIRNAME)
        if idx + 1 < len(parts) and parts[idx + 1] == TMP_DIRNAME:
            return True
    return False


def _file_size_on_disk(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def reconcile_workspace_usage(workspace_root: Path) -> QuotaUsage:
    root = _resolve_workspace_root(workspace_root)
    used_bytes = 0
    file_count = 0
    if root.is_dir():
        for item in root.rglob("*"):
            if not item.is_file():
                continue
            if _is_quota_excluded(item, root):
                continue
            used_bytes += _file_size_on_disk(item)
            file_count += 1
    usage = QuotaUsage(
        version=1,
        used_bytes=used_bytes,
        file_count=file_count,
        last_reconciled_at=datetime.now(UTC).isoformat(),
    )
    state_path = quota_state_path(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(usage.to_dict(), indent=2) + "\n", encoding="utf-8")
    return usage


def load_quota_usage(workspace_root: Path) -> QuotaUsage:
    root = _resolve_workspace_root(workspace_root)
    path = quota_state_path(root)
    if not path.is_file():
        return reconcile_workspace_usage(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return QuotaUsage.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return reconcile_workspace_usage(root)


def save_quota_usage(workspace_root: Path, usage: QuotaUsage) -> None:
    root = _resolve_workspace_root(workspace_root)
    path = quota_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(usage.to_dict(), indent=2) + "\n", encoding="utf-8")


def check_workspace_write(
    *,
    profile: str,
    workspace_root: Path,
    target: Path,
    new_payload_bytes: int,
    previous_size: int = 0,
) -> None:
    safe_profile = validate_profile_name(profile)
    root = _resolve_workspace_root(workspace_root)
    if _is_quota_excluded(target, root):
        return

    limits = load_profile_limits(safe_profile) or ensure_profile_limits(safe_profile)
    usage = load_quota_usage(root)

    projected_bytes = usage.used_bytes - max(0, previous_size) + new_payload_bytes
    if projected_bytes > limits.workspace_max_bytes:
        raise WorkspaceQuotaExceeded(
            f"Workspace quota exceeded for profile '{safe_profile}': "
            f"{projected_bytes} bytes > {limits.workspace_max_bytes} bytes "
            f"(tariff: {limits.tariff_id})"
        )

    is_new_file = not target.exists()
    projected_files = usage.file_count + (1 if is_new_file else 0)
    if projected_files > limits.workspace_max_files:
        raise WorkspaceQuotaExceeded(
            f"Workspace file count limit exceeded for profile '{safe_profile}': "
            f"{projected_files} > {limits.workspace_max_files} (tariff: {limits.tariff_id})"
        )


def apply_workspace_write_delta(
    workspace_root: Path,
    *,
    old_size: int,
    new_size: int,
    created: bool,
) -> QuotaUsage:
    root = _resolve_workspace_root(workspace_root)
    usage = load_quota_usage(root)
    used = usage.used_bytes - max(0, old_size) + max(0, new_size)
    count = usage.file_count + (1 if created else 0)
    updated = QuotaUsage(
        version=usage.version,
        used_bytes=max(0, used),
        file_count=max(0, count),
        last_reconciled_at=datetime.now(UTC).isoformat(),
    )
    save_quota_usage(root, updated)
    return updated


def quota_status(profile: str, workspace_root: Path) -> tuple[ProfileLimits, QuotaUsage]:
    safe_profile = validate_profile_name(profile)
    root = _resolve_workspace_root(workspace_root)
    limits = load_profile_limits(safe_profile) or ensure_profile_limits(safe_profile)
    usage = load_quota_usage(root)
    return limits, usage


def plaintext_size_hint(path: Path) -> int:
    """Estimate on-disk size after encryption for quota pre-check."""
    if not path.is_file():
        return 0
    size = _file_size_on_disk(path)
    if is_encrypted_file(path):
        return size
    return size + len(ENCRYPTION_MAGIC) + 12 + 16