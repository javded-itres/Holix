"""HTTP smoke tests for Holix Studio router."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from integrations.desktop.app import create_studio_app
from integrations.desktop.security import StudioSecurityPolicy


@pytest.fixture
def studio_client(tmp_path, monkeypatch):
    home = tmp_path / "holix"
    monkeypatch.setenv("HOLIX_HOME", str(home))
    profile = "router_test"
    profile_dir = home / "profiles" / profile
    ws = profile_dir / "workspace"
    ws.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        "profile_name: router_test\nworkspace_jail_enabled: false\n",
        encoding="utf-8",
    )
    (ws / "main.py").write_text("x = 1\n", encoding="utf-8")

    policy = StudioSecurityPolicy(
        host="127.0.0.1",
        token="test-token",
        token_generated=False,
        allow_lan=False,
        is_production=False,
    )
    app = create_studio_app(policy, profile, serve_cwd=ws)
    return TestClient(app), profile


def test_health_no_auth(studio_client) -> None:
    client, _ = studio_client
    res = client.get("/studio/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_files_tree_requires_auth(studio_client) -> None:
    client, _ = studio_client
    res = client.get("/studio/api/files/tree")
    assert res.status_code == 401


def test_files_tree_with_token(studio_client) -> None:
    client, _ = studio_client
    res = client.get(
        "/studio/api/files/tree",
        headers={"Authorization": "Bearer test-token"},
    )
    assert res.status_code == 200
    names = {c["name"] for c in res.json()["children"]}
    assert "main.py" in names


def test_files_read(studio_client) -> None:
    client, _ = studio_client
    res = client.get(
        "/studio/api/files/read?path=main.py",
        headers={"Authorization": "Bearer test-token"},
    )
    assert res.status_code == 200
    assert res.json()["content"] == "x = 1\n"


def test_studio_index(studio_client) -> None:
    client, _ = studio_client
    res = client.get("/studio/?token=test-token")
    assert res.status_code == 200
    assert "Holix Studio" in res.text
    assert "HOLIX_STUDIO_TOKEN" in res.text


def test_files_write_and_upload(studio_client) -> None:
    client, _ = studio_client
    headers = {"Authorization": "Bearer test-token"}
    res = client.post(
        "/studio/api/files/write",
        headers=headers,
        json={"path": "new.txt", "content": "draft", "create_only": True},
    )
    assert res.status_code == 200
    assert res.json()["path"] == "new.txt"

    res = client.get("/studio/api/files/read?path=new.txt", headers=headers)
    assert res.json()["content"] == "draft"

    res = client.post(
        "/studio/api/files/upload",
        headers=headers,
        data={"directory": ""},
        files={"file": ("uploaded.txt", b"from browser", "text/plain")},
    )
    assert res.status_code == 200
    assert res.json()["path"] == "uploaded.txt"


def test_files_mkdir(studio_client) -> None:
    client, _ = studio_client
    headers = {"Authorization": "Bearer test-token"}
    res = client.post(
        "/studio/api/files/mkdir",
        headers=headers,
        json={"path": "src/components"},
    )
    assert res.status_code == 200
    assert res.json()["path"] == "src/components"
    assert res.json()["kind"] == "directory"

    tree = client.get("/studio/api/files/tree", headers=headers).json()
    names = {c["name"] for c in tree["children"]}
    assert "src" in names

    res = client.post(
        "/studio/api/files/mkdir",
        headers=headers,
        json={"path": "src/components"},
    )
    assert res.status_code == 409


def test_assets_without_auth(studio_client) -> None:
    client, _ = studio_client
    res = client.get("/studio/assets/styles.css")
    assert res.status_code == 200
    assert "color-scheme" in res.text