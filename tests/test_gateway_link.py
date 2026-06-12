"""Holix Link gateway pairing and WebSocket relay."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from cli.core import ProfileManager
from core.gateway.link_relay import LinkRelay
from core.gateway.links_store import LinksStore
from fastapi.testclient import TestClient
from integrations.link.protocol import RpcOp, RpcResult, WsMessageType


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def link_client(gateway_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import api.state

    monkeypatch.setattr(api.state, "links_store", LinksStore())
    monkeypatch.setattr(api.state, "link_relay", LinkRelay())
    return gateway_client


def _create_support_profile(holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("support")


def test_create_and_pair_link(link_client: TestClient, gateway_auth_headers: dict, holix_home: Path) -> None:
    _create_support_profile(holix_home)

    created = link_client.post(
        "/v1/link/create",
        headers=gateway_auth_headers,
        json={"profile": "support", "ttl_seconds": 600},
    )
    assert created.status_code == 200
    code = created.json()["code"]
    assert code.startswith("LINK-")

    paired = link_client.post(
        "/v1/link/pair",
        json={
            "code": code,
            "folder": "/home/user/acme",
            "device_public_key_b64": "cHVibGljLWtleQ==",
        },
    )
    assert paired.status_code == 200
    body = paired.json()
    assert body["link_id"].startswith("link_")
    assert body["gateway_ws_url"].endswith("/v1/link/ws")
    assert body["permissions"]["read"] is True


def test_pair_rejects_used_code(link_client: TestClient, gateway_auth_headers: dict, holix_home: Path) -> None:
    _create_support_profile(holix_home)

    created = link_client.post(
        "/v1/link/create",
        headers=gateway_auth_headers,
        json={"profile": "support"},
    )
    code = created.json()["code"]
    payload = {
        "code": code,
        "folder": "~/work",
        "device_public_key_b64": "a2V5",
    }
    assert link_client.post("/v1/link/pair", json=payload).status_code == 200
    again = link_client.post("/v1/link/pair", json=payload)
    assert again.status_code == 410


def test_link_max_connections_limit(link_client: TestClient, gateway_auth_headers: dict, holix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("limited")
    config_path = manager.get_profile_dir("limited") / "config.yaml"
    config_path.write_text(
        yaml.dump({"link": {"max_connections": 1}}),
        encoding="utf-8",
    )

    created = link_client.post(
        "/v1/link/create",
        headers=gateway_auth_headers,
        json={"profile": "limited"},
    )
    code = created.json()["code"]
    first = link_client.post(
        "/v1/link/pair",
        json={"code": code, "folder": "a", "device_public_key_b64": "a"},
    )
    assert first.status_code == 200

    created2 = link_client.post(
        "/v1/link/create",
        headers=gateway_auth_headers,
        json={"profile": "limited"},
    )
    second = link_client.post(
        "/v1/link/pair",
        json={
            "code": created2.json()["code"],
            "folder": "b",
            "device_public_key_b64": "b",
        },
    )
    assert second.status_code == 409


def test_list_and_revoke_link(link_client: TestClient, gateway_auth_headers: dict, holix_home: Path) -> None:
    _create_support_profile(holix_home)

    created = link_client.post(
        "/v1/link/create",
        headers=gateway_auth_headers,
        json={"profile": "support"},
    )
    paired = link_client.post(
        "/v1/link/pair",
        json={
            "code": created.json()["code"],
            "folder": "docs",
            "device_public_key_b64": "cHVibGlj",
        },
    )
    link_id = paired.json()["link_id"]

    listed = link_client.get(
        "/v1/link/list?profile=support",
        headers=gateway_auth_headers,
    )
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["links"][0]["link_id"] == link_id
    assert listed.json()["links"][0]["online"] is False

    revoked = link_client.post(f"/v1/link/revoke/{link_id}", headers=gateway_auth_headers)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_websocket_auth_and_rpc_result(link_client: TestClient, gateway_auth_headers: dict, holix_home: Path) -> None:
    _create_support_profile(holix_home)

    created = link_client.post(
        "/v1/link/create",
        headers=gateway_auth_headers,
        json={"profile": "support"},
    )
    paired = link_client.post(
        "/v1/link/pair",
        json={
            "code": created.json()["code"],
            "folder": "src",
            "device_public_key_b64": "ZGV2aWNl",
        },
    )
    link_id = paired.json()["link_id"]

    with link_client.websocket_connect("/v1/link/ws") as ws:
        ws.send_json({
            "type": WsMessageType.AUTH,
            "link_id": link_id,
            "device_public_key_b64": "ZGV2aWNl",
            "nonce": "n1",
        })
        auth_ok = ws.receive_json()
        assert auth_ok["type"] == WsMessageType.AUTH_OK
        assert auth_ok["link_id"] == link_id

        status = link_client.get(f"/v1/link/{link_id}", headers=gateway_auth_headers)
        assert status.json()["online"] is True

        ws.send_json({"type": WsMessageType.PING, "ts": 1.0})
        pong = ws.receive_json()
        assert pong["type"] == WsMessageType.PONG

    import api.state

    relay = api.state.link_relay
    assert relay is not None
    assert not relay.is_online(link_id)


@pytest.mark.asyncio
async def test_relay_call_rpc_roundtrip(holix_home: Path) -> None:
    from unittest.mock import AsyncMock

    from core.gateway.link_relay import LinkRelay
    from integrations.link.protocol import RpcCall

    relay = LinkRelay()
    websocket = AsyncMock()

    sent: list[dict] = []

    async def _send_json(data: dict) -> None:
        sent.append(data)

    websocket.send_json = _send_json
    await relay.register("link_test", websocket)

    call = RpcCall(id="req-1", op=RpcOp.STAT, path=".")
    task = __import__("asyncio").create_task(relay.call_rpc("link_test", call, timeout=2.0))
    await __import__("asyncio").sleep(0.05)
    assert sent and sent[0]["op"] == RpcOp.STAT

    await relay.handle_client_message(
        "link_test",
        RpcResult(id="req-1", ok=True, payload={"stat": {"path": ".", "is_dir": True, "size": 0}}).model_dump(),
    )
    result = await task
    assert result.ok is True