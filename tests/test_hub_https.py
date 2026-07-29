"""Hub install source security (audit #7)."""

from __future__ import annotations

import pytest
from core.hub.sources import parse_install_source


def test_http_skill_url_rejected() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        parse_install_source("http://evil.example/SKILL.md")


def test_https_skill_url_ok() -> None:
    p = parse_install_source("https://example.com/path/SKILL.md")
    assert p.kind == "url"
    assert p.ref.startswith("https://")
