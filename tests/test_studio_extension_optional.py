"""Studio extension is optional in core-only installs."""

from __future__ import annotations

import pytest

from core.extensions.registry import get_extension


def test_studio_extension_optional() -> None:
    """Without holix-studio installed, studio extension may be absent."""
    ext = get_extension("studio")
    if ext is None:
        pytest.skip("holix-studio not installed")
    assert ext.name == "studio"