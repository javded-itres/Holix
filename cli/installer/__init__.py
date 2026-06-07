"""Cross-platform Helix installation helpers."""

from cli.installer.manifest import InstallManifest, load_manifest, save_manifest
from cli.installer.system import (
    InstallOptions,
    InstallResult,
    detect_repo_root,
    install_helix,
    record_install,
    scripts_bin_dir,
    verify_helix_on_path,
)
from cli.installer.update import UpdateOptions, UpdateResult, update_helix

__all__ = [
    "InstallManifest",
    "InstallOptions",
    "InstallResult",
    "UpdateOptions",
    "UpdateResult",
    "detect_repo_root",
    "install_helix",
    "load_manifest",
    "record_install",
    "save_manifest",
    "scripts_bin_dir",
    "update_helix",
    "verify_helix_on_path",
]