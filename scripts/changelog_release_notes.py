#!/usr/bin/env python3
"""Extract GitHub release notes for a version from docs/CHANGELOG.md."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"

INSTALL_FOOTER = (
    "\n\n**Install:** `pipx install HelixAgentAi` or `pip install -U HelixAgentAi`"
)


def extract_release_notes(version: str, *, changelog_text: str | None = None) -> str:
    """Return markdown body for GitHub release notes."""
    text = changelog_text if changelog_text is not None else CHANGELOG.read_text(encoding="utf-8")
    pattern = rf"^## {re.escape(version)} — .+?\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f"No changelog section for version {version}")
    body = match.group(1).strip()
    if INSTALL_FOOTER.strip() not in body:
        body += INSTALL_FOOTER
    return body


def main() -> None:
    version = sys.argv[1].removeprefix("v").strip()
    if not version:
        raise SystemExit("usage: changelog_release_notes.py <version>")
    print(extract_release_notes(version))


if __name__ == "__main__":
    main()