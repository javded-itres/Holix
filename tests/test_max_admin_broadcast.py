"""Admin broadcast to MAX users."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.max.admin import set_admin_user
from integrations.max.admin_broadcast import (
    AdminBroadcastDraft,
    format_broadcast_html,
    resolve_broadcast_recipients,
    try_compose_admin_broadcast,
)
from integrations.max.env_store import save_max_env
from integrations.max.session import MaxChatSession
from integrations.max.user_profiles import set_user_profile


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


def _setup_bot(holix_home) -> None:
    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile="shared")
    set_admin_user("shared", 900)
    set_user_profile("shared", 101, "alice")
    set_user_profile("shared", 102, "bob")


def test_resolve_recipients_all_excludes_admin(holix_home) -> None:
    _setup_bot(holix_home)
    recipients = resolve_broadcast_recipients("shared", "all", exclude_user_id=900)
    assert recipients == [(101, "alice"), (102, "bob")]


def test_resolve_recipients_single_profile(holix_home) -> None:
    _setup_bot(holix_home)
    recipients = resolve_broadcast_recipients("shared", "alice", exclude_user_id=900)
    assert recipients == [(101, "alice")]


def test_format_broadcast_html_escapes_content() -> None:
    html = format_broadcast_html("<script>", target="all")
    assert "&lt;script&gt;" in html
    assert "администратора" in html


@pytest.mark.asyncio
async def test_compose_sends_and_clears_draft(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_bot(holix_home)
    from cli.core import ProfileManager

    ProfileManager().create_profile("alice", inherit_global=True)
    ProfileManager().create_profile("bob", inherit_global=True)

    session = MaxChatSession(
        user_id=900,
        profile="admin",
        conversation_id="max_admin_900",
        bot_profile="shared",
        pending_admin_broadcast=AdminBroadcastDraft(target="all"),
    )
    host = MagicMock()
    host._session = session
    host._client = MagicMock()
    host._send_html = AsyncMock()

    delivered: list[int] = []

    async def _fake_deliver(bot_profile, recipients, content, *, target, client=None):
        delivered.extend(uid for uid, _ in recipients)
        from integrations.max.admin_broadcast import BroadcastDeliveryResult

        return BroadcastDeliveryResult(sent=len(recipients))

    monkeypatch.setattr(
        "integrations.max.admin_broadcast.deliver_broadcast",
        _fake_deliver,
    )

    handled = await try_compose_admin_broadcast(host, "Hello everyone")
    assert handled is True
    assert session.pending_admin_broadcast is None
    assert delivered == [101, 102]
    host._send_html.assert_awaited_once()


@pytest.mark.asyncio
async def test_compose_ignored_for_non_admin(holix_home) -> None:
    _setup_bot(holix_home)
    session = MaxChatSession(
        user_id=101,
        profile="alice",
        conversation_id="max_alice_101",
        bot_profile="shared",
        pending_admin_broadcast=AdminBroadcastDraft(target="all"),
    )
    host = MagicMock()
    host._session = session
    assert await try_compose_admin_broadcast(host, "spam") is False
    assert session.pending_admin_broadcast is None