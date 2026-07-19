"""`/init` command behaviour across hosts."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cli.shared.commands.project_init import (
    choose_init_execution_mode,
    run_project_init,
)
from integrations.telegram.session import ChatSession


def test_choose_init_execution_mode_react_for_telegram() -> None:
    session = ChatSession(chat_id=1, user_id=1, profile="default", conversation_id="tg")
    host = SimpleNamespace(
        _session=session,
        _execution_modes=session.execution_modes,
        _execution_mode_index=0,
        _refresh_status_bar=lambda: None,
    )
    mode = choose_init_execution_mode(host)
    assert mode == "react"
    assert host._execution_mode_index == 0


def test_choose_init_execution_mode_plan_for_tui() -> None:
    host = SimpleNamespace(
        _execution_modes=["react", "plan_and_execute", "hybrid"],
        _execution_mode_index=0,
        _refresh_status_bar=lambda: None,
        config=SimpleNamespace(),
    )
    with patch("cli.shared.commands.project_init.settings", create=True):
        mode = choose_init_execution_mode(host)
    assert mode == "plan_and_execute"
    assert host._execution_mode_index == 1


def test_choose_init_execution_mode_react_for_studio_host() -> None:
    """Studio uses react for /init — avoids plan-review UI during onboarding."""

    class StudioSession:
        __module__ = "holix_studio.application.session"

        execution_modes = ["react", "plan_and_execute", "hybrid", "auto"]
        execution_mode_index = 0

    studio_session = StudioSession()
    host = SimpleNamespace(
        _session=studio_session,
        _execution_modes=studio_session.execution_modes,
        _execution_mode_index=0,
        _refresh_status_bar=lambda: None,
        config=SimpleNamespace(),
    )
    mode = choose_init_execution_mode(host)
    assert mode == "react"
    assert host._execution_mode_index == 0


@pytest.mark.asyncio
async def test_run_project_init_warns_when_agent_busy() -> None:
    session = ChatSession(chat_id=1, user_id=1, profile="default", conversation_id="tg")
    await session.run_lock.acquire()
    try:
        host = MagicMock()
        host.profile = "default"
        host.agent = MagicMock()
        host._session = session
        host._send_plain = AsyncMock()
        host._send_message = AsyncMock()

        await run_project_init(host)

        host.transcript_write.assert_called_once()
        msg = str(host.transcript_write.call_args).lower()
        assert "busy" in msg or "занят" in msg
        host._send_message.assert_not_called()
    finally:
        session.run_lock.release()


@pytest.mark.asyncio
async def test_run_project_init_starts_agent_on_telegram(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    session = ChatSession(chat_id=1, user_id=1, profile="default", conversation_id="tg")
    host = MagicMock()
    host.profile = "default"
    host.agent = MagicMock()
    host._session = session
    host._execution_modes = session.execution_modes
    host._execution_mode_index = 0
    host._refresh_status_bar = MagicMock()
    host.emit_system = None
    host._send_plain = AsyncMock()
    host._send_message = AsyncMock()

    await run_project_init(host)

    host._send_plain.assert_awaited_once()
    host._send_message.assert_awaited_once()
    assert session.execution_mode == "react"
    assert (tmp_path / ".holix" / "HOLIX.md").is_file()
    prompt = host._send_message.await_args.args[0]
    assert "Pre-scan" in prompt
    assert "~20 `read_file`" in prompt
    assert "patch_file" in prompt


@pytest.mark.asyncio
async def test_telegram_stop_cancels_run_tasks() -> None:
    from integrations.telegram.host import TelegramHost

    bot = MagicMock()
    session = ChatSession(chat_id=1, user_id=1, profile="default", conversation_id="tg")
    host = TelegramHost(bot, session)

    async def sleeper() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(sleeper())
    host._run_tasks.add(task)

    host._action_stop_all()
    await asyncio.sleep(0.05)
    assert task.cancelled() or task.done()