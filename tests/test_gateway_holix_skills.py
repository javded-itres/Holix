"""Tests for /api/holix/profiles/{id}/skills routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_skills_list_and_assignments(
    holix_home: Path,
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("skills-test")

    listed = gateway_client.get(
        "/api/holix/profiles/skills-test/skills",
        headers=gateway_auth_headers,
    )
    assert listed.status_code == 200
    assert "skills" in listed.json()

    seeded = gateway_client.post(
        "/api/holix/profiles/skills-test/skills/seed-bundled",
        headers=gateway_auth_headers,
    )
    assert seeded.status_code == 200

    patched = gateway_client.patch(
        "/api/holix/profiles/skills-test/skills/assignments",
        headers=gateway_auth_headers,
        json={"assignments": {"main": ["holix-cron"]}},
    )
    assert patched.status_code == 200
    assert patched.json()["reload_required"] is True

    assignments = gateway_client.get(
        "/api/holix/profiles/skills-test/skills/assignments",
        headers=gateway_auth_headers,
    )
    assert assignments.status_code == 200
    assert assignments.json()["assignments"]["main"] == ["holix-cron"]