"""OpenSpec-compatible path helpers under ``openspec/``."""

from __future__ import annotations

import re
from pathlib import Path

OPENSPEC_DIR = "openspec"
SPECS_DIR = "specs"
CHANGES_DIR = "changes"
ARCHIVE_DIR = "archive"
CONFIG_FILE = "config.yaml"
APPLY_MODE_FILE = ".apply-mode"
SPEC_FILENAME = "spec.md"

_CHANGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,63}$")


def openspec_root(workspace: Path) -> Path:
    return Path(workspace) / OPENSPEC_DIR


def config_path(workspace: Path) -> Path:
    return openspec_root(workspace) / CONFIG_FILE


def specs_root(workspace: Path) -> Path:
    return openspec_root(workspace) / SPECS_DIR


def domain_spec_path(workspace: Path, domain: str) -> Path:
    return specs_root(workspace) / domain / SPEC_FILENAME


def changes_root(workspace: Path) -> Path:
    return openspec_root(workspace) / CHANGES_DIR


def change_dir(workspace: Path, change_id: str) -> Path:
    return changes_root(workspace) / change_id


def archive_root(workspace: Path) -> Path:
    return changes_root(workspace) / ARCHIVE_DIR


def apply_mode_path(workspace: Path, change_id: str) -> Path:
    return change_dir(workspace, change_id) / APPLY_MODE_FILE


def validate_change_id(change_id: str) -> str:
    cid = (change_id or "").strip().lower().replace(" ", "-")
    if not _CHANGE_ID_RE.match(cid):
        raise ValueError(
            "change_id must be 1–64 chars: lowercase letters, digits, hyphen, underscore "
            f"(got {change_id!r})"
        )
    if cid == ARCHIVE_DIR:
        raise ValueError(f"change_id cannot be reserved name {ARCHIVE_DIR!r}")
    return cid


def validate_domain(domain: str) -> str:
    d = (domain or "").strip().lower().replace(" ", "-")
    if not _CHANGE_ID_RE.match(d):
        raise ValueError(f"invalid domain name: {domain!r}")
    return d
