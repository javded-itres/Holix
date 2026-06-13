"""Project version helpers (pyproject.toml + cli/__init__.py)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_VERSION_RE = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
_INIT_VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)

_BUILD_VERSION_ENV = "HOLIX_BUILD_VERSION"


def project_root(start: Path | None = None) -> Path:
    return start or Path(__file__).resolve().parents[1]


def read_version(root: Path | None = None) -> str:
    text = (project_root(root) / "pyproject.toml").read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if not match:
        raise ValueError("version not found in pyproject.toml")
    return match.group(1)


def bump_patch(version: str) -> str:
    parts = version.strip().split(".")
    if len(parts) < 3:
        parts.extend(["0"] * (3 - len(parts)))
    major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    return f"{major}.{minor}.{patch + 1}"


def write_version(new_version: str, root: Path | None = None) -> str:
    base = project_root(root)
    pyproject = base / "pyproject.toml"
    py_text = pyproject.read_text(encoding="utf-8")
    if not _VERSION_RE.search(py_text):
        raise ValueError("version not found in pyproject.toml")
    pyproject.write_text(_VERSION_RE.sub(f'version = "{new_version}"', py_text, count=1), encoding="utf-8")

    init_py = base / "cli" / "__init__.py"
    init_text = init_py.read_text(encoding="utf-8")
    if not _INIT_VERSION_RE.search(init_text):
        raise ValueError("__version__ not found in cli/__init__.py")
    init_py.write_text(
        _INIT_VERSION_RE.sub(f'__version__ = "{new_version}"', init_text, count=1),
        encoding="utf-8",
    )
    return new_version


def bump_project_version(root: Path | None = None) -> str:
    current = read_version(root)
    return write_version(bump_patch(current), root)


def resolve_build_version(current: str, *, bump: bool = True, root: Path | None = None) -> str:
    """Return version for this build; bump at most once per process (sdist + wheel)."""
    if os.environ.get("HOLIX_NO_VERSION_BUMP"):
        return current

    cached = os.environ.get(_BUILD_VERSION_ENV)
    if cached:
        return cached

    new_version = bump_patch(current) if bump else current
    write_version(new_version, root)
    os.environ[_BUILD_VERSION_ENV] = new_version
    return new_version


def apply_metadata_version(metadata: object, new_version: str) -> None:
    metadata._version = new_version  # type: ignore[attr-defined]
    metadata.core._version = new_version  # type: ignore[attr-defined]
    metadata.core_raw_metadata["version"] = new_version  # type: ignore[attr-defined]