"""Doctor checks for Holix Link."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.doctor.checks import run_all_checks
from core.gateway.links_store import LinksStore
from integrations.link.protocol import LinkPermissions


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    from cli.core import ProfileManager

    ProfileManager().create_profile("default")
    return tmp_path


@pytest.mark.asyncio
async def test_doctor_reports_offline_links(holix_home: Path) -> None:
    store = LinksStore()
    store.create_link(
        profile="default",
        folder_portable="/tmp/work",
        device_public_key_b64="a",
        permissions=LinkPermissions(),
    )

    findings = await run_all_checks("default", skip_llm_check=True)
    link_findings = [f for f in findings if f.code == "link.status"]
    assert link_findings
    assert "active link" in link_findings[0].detail.lower()
    assert "gateway" in link_findings[0].recommendation.lower()