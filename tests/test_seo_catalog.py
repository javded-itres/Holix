"""SEO catalog completeness for web-docs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB_DOCS = REPO / "web-docs"


def test_seo_catalog_covers_all_nav_slugs() -> None:
    sys.path.insert(0, str(WEB_DOCS))
    from seo_catalog import SEO_PAGES  # noqa: WPS433

    nav = json.loads((WEB_DOCS / "nav.json").read_text(encoding="utf-8"))
    slugs = {item["slug"] for item in nav}
    catalog_slugs = set(SEO_PAGES)
    assert catalog_slugs >= slugs, f"Missing SEO entries for: {sorted(slugs - catalog_slugs)}"


def test_seo_meta_has_curated_descriptions() -> None:
    subprocess.run(
        [sys.executable, str(WEB_DOCS / "build.py")],
        cwd=str(WEB_DOCS),
        check=True,
        timeout=120,
    )
    meta = json.loads((WEB_DOCS / "seo-meta.json").read_text(encoding="utf-8"))
    install_ru = meta["pages"]["installation"]["ru"]
    assert "pipx" in install_ru["description"].lower() or "PyPI" in install_ru["description"]
    assert len(install_ru["description"]) >= 80
    assert install_ru["keywords"]
    assert meta["views"]["docs-hub"]["en"]["title"]
    assert meta["views"]["home"]["ru"]["description"]