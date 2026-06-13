"""Log rotation helpers."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from config import settings


def _rotated_name(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.{index}")


def rotate_file(
    path: Path,
    *,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> list[Path]:
    """Rotate *path* when it exceeds *max_bytes*. Returns created archive paths."""
    if not path.exists() or path.stat().st_size == 0:
        return []

    limit = max_bytes if max_bytes is not None else settings.log_max_bytes
    keep = backup_count if backup_count is not None else settings.log_backup_count
    if path.stat().st_size < limit:
        return []

    created: list[Path] = []
    for i in range(keep - 1, 0, -1):
        src = _rotated_name(path, i)
        dst = _rotated_name(path, i + 1)
        if src.exists():
            if dst.exists():
                dst.unlink()
            src.rename(dst)

    archive = _rotated_name(path, 1)
    shutil.copy2(path, archive)
    path.write_text("", encoding="utf-8")
    created.append(archive)
    return created


def rotate_all_known(profile: str = "default") -> list[Path]:
    """Rotate all standard Holix log files that exceed size limits."""
    from core.logging.paths import discover_log_files

    rotated: list[Path] = []
    for info in discover_log_files(profile):
        rotated.extend(rotate_file(info.path))
    return rotated


def purge_old_rotations(profile: str = "default") -> int:
    """Delete rotated backups older than log_rotation_days. Returns count removed."""
    from core.logging.paths import discover_log_files

    cutoff_days = settings.log_rotation_days
    if cutoff_days <= 0:
        return 0

    now = datetime.now(UTC).timestamp()
    removed = 0
    for info in discover_log_files(profile):
        base = info.path
        parent = base.parent
        pattern = f"{base.name}.*"
        for candidate in parent.glob(pattern):
            if candidate == base:
                continue
            try:
                age_days = (now - candidate.stat().st_mtime) / 86400
                if age_days > cutoff_days:
                    candidate.unlink()
                    removed += 1
            except OSError:
                pass
    return removed