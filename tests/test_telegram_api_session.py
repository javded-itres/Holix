"""The regular Telegram agent uses the local forward when it is listening."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_forward_resolver_points_telegram_at_the_local_port(monkeypatch) -> None:
    from integrations.telegram import api_session

    monkeypatch.setattr(api_session, "_forward_open", lambda: True)
    resolver = api_session.TelegramForwardResolver()
    rows = await resolver.resolve("api.telegram.org.", 443)
    assert rows[0]["host"] == "127.0.0.1"
    assert rows[0]["port"] == 1443
    assert rows[0]["hostname"] == "api.telegram.org"
    await resolver.close()
