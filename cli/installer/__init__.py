"""Cross-platform Holix installation helpers."""

from cli.installer.manifest import InstallManifest, load_manifest, save_manifest
from cli.installer.system import (
    InstallOptions,
    InstallResult,
    detect_repo_root,
    install_holix,
    record_install,
    scripts_bin_dir,
    verify_holix_on_path,
)
from cli.installer.bootstrap import BootstrapOptions, run_bootstrap_setup_sync
from cli.installer.pypi import PyPIInstallResult, install_from_pypi
from cli.installer.update import UpdateOptions, UpdateResult, update_holix

__all__ = [
    "BootstrapOptions",
    "PyPIInstallResult",
    "install_from_pypi",
    "run_bootstrap_setup_sync",
    "InstallManifest",
    "InstallOptions",
    "InstallResult",
    "UpdateOptions",
    "UpdateResult",
    "detect_repo_root",
    "install_holix",
    "load_manifest",
    "record_install",
    "save_manifest",
    "scripts_bin_dir",
    "update_holix",
    "verify_holix_on_path",
]