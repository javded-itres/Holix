"""Public extras must resolve on PyPI (no workspace-only packages)."""

from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_UNPUBLISHED = frozenset({"holix-extension-demo", "holix-studio"})


def _optional_deps() -> dict[str, list[str]]:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return dict(data["project"]["optional-dependencies"])


def test_all_extra_has_no_unpublished_packages() -> None:
    extras = _optional_deps()
    assert "all" in extras
    joined = " ".join(extras["all"]).lower()
    for name in _UNPUBLISHED:
        assert name not in joined, f"{name} must not be in Holix[all] (not on PyPI)"


def test_demo_extra_keeps_workspace_package() -> None:
    extras = _optional_deps()
    assert any("holix-extension-demo" in dep for dep in extras["demo"])
