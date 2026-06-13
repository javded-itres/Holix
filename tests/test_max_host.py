"""MAX host agent run lifecycle."""

from __future__ import annotations

import asyncio

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.max.host import MaxHost
from integrations.max.session import MaxChatSession


@pytest.mark.asyncio
async def test_handle_user_text_starts_agent_run_in_background() -> None:
    client = MagicMock()
    session = MaxChatSession(user_id=1, profile="default", conversation_id="max_default_1")
    session.agent = MagicMock()
    host = MaxHost(client, session)

    run_started = asyncio.Event()
    run_finished = asyncio.Event()

    async def fake_run(user_input: str) -> None:
        run_started.set()
        run_finished.set()

    host._run_agent = fake_run  # type: ignore[method-assign]

    with patch(
        "core.subagents.interaction.try_route_subagent_reply",
        return_value=(False, ""),
    ):
        await host.handle_user_text("hello")

    await asyncio.wait_for(run_started.wait(), timeout=1.0)
    await asyncio.wait_for(run_finished.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_run_agent_calls_presenter_finish_in_finally() -> None:
    client = MagicMock()
    session = MaxChatSession(
        user_id=1,
        profile="default",
        conversation_id="max_default_1",
        reply_user_id=1,
    )
    agent = MagicMock()
    agent.model = "smart"
    session.agent = agent
    host = MaxHost(client, session)

    finish_calls = 0

    class FakePresenter:
        final_delivered = False

        async def start(self) -> None:
            return None

        async def finish(self) -> None:
            nonlocal finish_calls
            finish_calls += 1

    class _Events:
        def subscribe(self, _handler):
            return None

        def unsubscribe(self, _handler):
            return None

    agent.events = _Events()

    async def fake_run_holix(*_args, **_kwargs):
        if False:
            yield None

    with (
        patch(
            "integrations.max.host.MaxLivePresenter",
            side_effect=lambda *a, **k: FakePresenter(),
        ),
        patch("integrations.max.event_handler.MaxEventHandler"),
        patch("integrations.max.approvals.MaxApprovals"),
        patch("integrations.max.config.load_max_settings") as load_settings,
        patch("core.runtime.executor.run_holix", side_effect=fake_run_holix),
        patch("core.session_models.ensure_session_model"),
        patch("core.tools.execution_context.chat_delivery_scope", return_value="token"),
        patch("core.tools.execution_context.reset_chat_delivery_scope"),
        patch("core.workspace.agent_path_visibility_context") as vis_ctx,
        patch("integrations.max.admin.is_max_admin", return_value=False),
    ):
        vis_ctx.return_value.__enter__ = MagicMock(return_value=None)
        vis_ctx.return_value.__exit__ = MagicMock(return_value=False)
        load_settings.return_value = MagicMock(
            edit_interval_ms=700,
            heartbeat_interval_s=45,
        )
        await host._run_agent("status please")

    assert finish_calls == 1