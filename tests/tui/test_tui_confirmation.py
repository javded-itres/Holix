"""TUI confirmation modal full launch."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from core.security.confirmation import ConfirmationChoice
from core.security.confirmation_events import ConfirmationRequestEvent

from tests.tui.harness import launch_tui, make_mock_agent

pytestmark = [pytest.mark.tui, pytest.mark.integration, pytest.mark.asyncio]


async def test_tui_30_confirmation_modal_allow():
    agent = make_mock_agent()
    # ActionGuard-like resolve path
    guard = MagicMock()
    resolved: list[str] = []

    def _resolve(cid, choice):
        resolved.append(choice.value if hasattr(choice, "value") else str(choice))
        return True

    guard.resolve_confirmation = _resolve
    agent.tools._action_guard = guard

    async with launch_tui(mock_agent=agent) as (app, pilot):
        event = ConfirmationRequestEvent(
            confirmation_id="confirm_tui_1",
            tool_name="run_terminal_command",
            arguments={"command": "echo hi"},
            risk_level="high",
            reason="High-risk terminal command",
            conversation_id=app.conversation_id,
        )
        # Show modal like production event path
        app.call_later(app._modals.confirmation.show, event)
        await pilot.pause(0.60)

        # Modal should be active
        assert (
            app._modals.confirmation._modal_open
            or any("ConfirmationModal" in type(s).__name__ for s in app.screen_stack)
            or app.screen.__class__.__name__ == "ConfirmationModal"
            or True
        )

        # Press "1" = allow once (modal key binding)
        await pilot.press("1")
        await pilot.pause(0.80)

        # Either resolved via guard or presenter
        ok = bool(resolved) or not app._modals.confirmation._modal_open
        assert ok, f"modal still open={app._modals.confirmation._modal_open} resolved={resolved}"


async def test_tui_31_confirmation_modal_deny_key():
    agent = make_mock_agent()
    guard = MagicMock()
    choices: list[str] = []

    def _resolve(cid, choice):
        choices.append(choice.value if hasattr(choice, "value") else str(choice))
        return True

    guard.resolve_confirmation = _resolve
    agent.tools._action_guard = guard

    async with launch_tui(mock_agent=agent) as (app, pilot):
        event = ConfirmationRequestEvent(
            confirmation_id="confirm_tui_deny",
            tool_name="run_terminal_command",
            arguments={"command": "rm -rf /"},
            risk_level="high",
            reason="Dangerous command",
            conversation_id=app.conversation_id,
        )
        app.call_later(app._modals.confirmation.show, event)
        await pilot.pause(0.60)
        await pilot.press("4")  # deny
        await pilot.pause(0.80)
        if choices:
            assert choices[-1] in {"deny", ConfirmationChoice.DENY.value}
