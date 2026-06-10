"""MCP path validation and error formatting."""

from __future__ import annotations

import pytest
from core.mcp.installer import build_config_from_popular
from core.mcp.popular import get_popular_by_key
from core.mcp.validate import format_mcp_error, normalize_allowed_paths


def test_normalize_allowed_paths_expands_cwd(tmp_path):
    valid, errs = normalize_allowed_paths(str(tmp_path))
    assert not errs
    assert len(valid) == 1
    assert valid[0] == str(tmp_path.resolve())


def test_normalize_rejects_missing():
    valid, errs = normalize_allowed_paths("/nonexistent/path/xyz")
    assert not valid
    assert errs


def test_build_filesystem_rejects_bad_path():
    pop = get_popular_by_key("filesystem")
    with pytest.raises(ValueError, match="does not exist"):
        build_config_from_popular(pop, {"allowed_paths": "/no/such/dir"})


def test_format_exception_group():
    try:
        raise ExceptionGroup("tg", [ValueError("ENOENT: path missing")])
    except ExceptionGroup as e:
        msg = format_mcp_error(e)
        assert "ENOENT" in msg