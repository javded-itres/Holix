"""Tests for CHANGELOG → GitHub release notes extraction."""

from __future__ import annotations

import pytest
from scripts.changelog_release_notes import extract_release_notes

SAMPLE_CHANGELOG = """# Changelog

## Unreleased

## 0.1.7 — 2026-06-10

### Added
- Feature A

### Fixed
- Bug B

## 0.1.6 — 2026-06-09

### Added
- Older feature
"""


def test_extract_release_notes_for_version() -> None:
    notes = extract_release_notes("0.1.7", changelog_text=SAMPLE_CHANGELOG)
    assert "### Added" in notes
    assert "Feature A" in notes
    assert "Bug B" in notes
    assert "Older feature" not in notes
    assert "pipx install HelixAgentAi" in notes


def test_extract_release_notes_missing_version() -> None:
    with pytest.raises(ValueError, match="No changelog section"):
        extract_release_notes("9.9.9", changelog_text=SAMPLE_CHANGELOG)


def test_extract_release_notes_from_repo_changelog() -> None:
    notes = extract_release_notes("0.1.7")
    assert "profile whitelist" in notes.lower()
    assert "pipx install HelixAgentAi" in notes