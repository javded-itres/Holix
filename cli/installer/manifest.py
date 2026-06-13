"""Persisted install metadata for ``holix update``."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from cli.core import HOLIX_HOME

MANIFEST_PATH = HOLIX_HOME / "install.json"


@dataclass(slots=True)
class InstallManifest:
    """How Holix was installed — drives update strategy."""

    version: str
    method: str  # uv-tool | uv-pip | pip
    scope: str  # user | system
    source: str  # git | local | pypi
    extras: list[str]
    installed_at: str
    repo_root: str | None = None
    holix_path: str | None = None
    bin_dir: str | None = None
    git_remote: str | None = None
    git_branch: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            version=str(data["version"]),
            method=str(data["method"]),
            scope=str(data.get("scope", "user")),
            source=str(data.get("source", "local")),
            extras=list(data.get("extras") or []),
            installed_at=str(data.get("installed_at", "")),
            repo_root=data.get("repo_root"),
            holix_path=data.get("holix_path"),
            bin_dir=data.get("bin_dir"),
            git_remote=data.get("git_remote"),
            git_branch=data.get("git_branch"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_manifest() -> InstallManifest | None:
    if not MANIFEST_PATH.exists():
        return None
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return InstallManifest.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_manifest(manifest: InstallManifest) -> None:
    HOLIX_HOME.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest.to_dict(), indent=2),
        encoding="utf-8",
    )


def build_manifest(
    *,
    version: str,
    method: str,
    scope: str,
    source: str,
    extras: tuple[str, ...],
    repo_root: Path | None,
    holix_path: Path | None,
    bin_dir: Path | None,
    git_remote: str | None = None,
    git_branch: str | None = None,
) -> InstallManifest:
    return InstallManifest(
        version=version,
        method=method,
        scope=scope,
        source=source,
        extras=list(extras),
        installed_at=datetime.now(UTC).isoformat(),
        repo_root=str(repo_root) if repo_root else None,
        holix_path=str(holix_path) if holix_path else None,
        bin_dir=str(bin_dir) if bin_dir else None,
        git_remote=git_remote,
        git_branch=git_branch,
    )