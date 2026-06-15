"""Tests for /api/holix/profiles/{id}/launch routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_launch_clis_and_sessions_list(
    holix_home: Path,
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("launch-api")

    clis = gateway_client.get(
        "/api/holix/profiles/launch-api/launch/clis",
        headers=gateway_auth_headers,
    )
    assert clis.status_code == 200
    body = clis.json()
    assert body["supported"] is True
    assert body["count"] >= 1
    assert any(row["cli_id"] == "claude" for row in body["clis"])

    sessions = gateway_client.get(
        "/api/holix/profiles/launch-api/launch/sessions",
        headers=gateway_auth_headers,
    )
    assert sessions.status_code == 200
    assert sessions.json()["count"] == 0


def test_launch_cli_start_via_api(
    holix_home: Path,
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("launch-run")
    fake_session = {
        "session_id": "abc123",
        "tmux_session": "holix-launch-run-claude-1",
        "cli_id": "claude",
        "profile": "launch-run",
        "cwd": str(holix_home),
        "model_slot": "coder",
        "model_name": "coder",
        "window_index": 0,
        "pane_index": 0,
        "task_preview": "build ui",
        "created_at": "2026-01-01T00:00:00+00:00",
        "last_output_at": "",
    }

    with patch(
        "api.routers.holix_launch.launch_external_cli",
        return_value=fake_session,
    ) as mock_launch:
        response = gateway_client.post(
            "/api/holix/profiles/launch-run/launch/claude",
            headers=gateway_auth_headers,
            json={"task": "build ui", "restart": False},
        )

    assert response.status_code == 200
    assert response.json()["session"]["session_id"] == "abc123"
    mock_launch.assert_called_once()


def test_launch_assignment_patch(
    holix_home: Path,
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    from cli.core import ProfileManager

    ProfileManager().create_profile("launch-assign")

    response = gateway_client.patch(
        "/api/holix/profiles/launch-assign/launch/claude/assignment",
        headers=gateway_auth_headers,
        json={"agent_slot": "coder"},
    )
    assert response.status_code == 200
    assert response.json()["binding"]["agent_slot"] == "coder"