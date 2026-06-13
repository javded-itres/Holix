"""Tests for curl/bootstrap installer helpers."""

from __future__ import annotations

from cli.installer.bootstrap import pypi_package_spec


def test_pypi_package_spec_minimal() -> None:
    assert pypi_package_spec(full=False) == "Holix"


def test_pypi_package_spec_full() -> None:
    assert pypi_package_spec(full=True) == "Holix[all]"