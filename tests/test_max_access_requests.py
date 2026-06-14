"""MAX access request queue and approval."""

from __future__ import annotations

import pytest
from integrations.max.access_approval import approve_access_request, reject_access_request_op
from integrations.max.access_requests import (
    STATUS_PENDING,
    get_access_request,
    list_pending_requests,
    register_access_request,
)


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    return root


def test_register_pending_request(holix_home) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile="bot")
    req, created = register_access_request(
        "bot",
        user_id=42,
        username="alice",
        first_name="Alice",
    )
    assert created is True
    assert req.status == STATUS_PENDING
    assert req.user_id == 42
    pending = list_pending_requests("bot")
    assert len(pending) == 1


def test_approve_access_request(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile="bot")
    register_access_request("bot", user_id=99, first_name="Bob")
    monkeypatch.setattr(
        "integrations.max.notify.notify_access_approved_sync",
        lambda *a, **k: None,
    )
    result = approve_access_request("bot", 99, create_profile="bob99")
    assert result.ok
    assert result.holix_profile == "bob99"
    assert get_access_request("bot", 99) is not None
    assert get_access_request("bot", 99).status == "approved"


def test_reject_access_request(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile="bot")
    register_access_request("bot", user_id=77, first_name="Eve")
    monkeypatch.setattr(
        "integrations.max.notify.notify_access_rejected_sync",
        lambda *a, **k: None,
    )
    result = reject_access_request_op("bot", 77)
    assert result.ok
    assert list_pending_requests("bot") == []