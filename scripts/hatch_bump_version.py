"""Hatch build hook: auto-increment patch version on each `uv build`."""

from __future__ import annotations

import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.versioning import apply_metadata_version, resolve_build_version  # noqa: E402


def _should_bump(root: str, target_name: str, build_variant: str) -> bool:
    """Bump only when HOLIX_AUTO_VERSION_BUMP=1 (off by default — version follows CHANGELOG)."""
    import os

    if os.environ.get("HOLIX_NO_VERSION_BUMP"):
        return False
    if os.environ.get("HOLIX_AUTO_VERSION_BUMP", "").strip() not in {"1", "true", "yes"}:
        return False
    if build_variant == "editable":
        return False
    # uv builds the wheel from the sdist in a fresh env (no .git) — version is already bumped.
    if target_name == "wheel" and not (Path(root) / ".git").is_dir():
        return False
    return True


class BumpVersionBuildHook(BuildHookInterface):

    def initialize(self, version: str, build_data: dict) -> None:
        if not _should_bump(self.root, self.target_name, version):
            return

        project_version = self.metadata.version
        new_version = resolve_build_version(project_version)
        apply_metadata_version(self.metadata, new_version)
        self.app.display_info(f"Holix build version: {new_version}")