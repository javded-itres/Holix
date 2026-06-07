"""Confirmation flow: modal + ActionGuard resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.security.confirmation import ConfirmationChoice
from core.subagents.interaction import resolve_any_confirmation
from core.security.confirmation_events import ConfirmationRequestEvent

from cli.tui.modals.confirmation import ConfirmationModal

if TYPE_CHECKING:
    from cli.tui.modals.stack import ModalStack


class ConfirmationPresenter:
    """Shows ConfirmationModal and resolves ActionGuard futures."""

    def __init__(self, app: Any, stack: ModalStack) -> None:
        self.app = app
        self._stack = stack

    def _resolve_guard_reference(self) -> None:
        agent = getattr(self.app, "agent", None)
        if agent and hasattr(agent, "tools") and agent.tools._action_guard:
            self.app._action_guard_reference = agent.tools._action_guard
        else:
            self.app._action_guard_reference = get_action_guard()

    def show(self, event: ConfirmationRequestEvent) -> None:
        self._resolve_guard_reference()
        self.app._pending_confirmation = event

        risk_emoji = {"no": "🟢", "low": "🔵", "medium": "🟡", "high": "🔴"}.get(
            event.risk_level, "⚠"
        )
        subagent = getattr(event, "subagent_name", "") or ""
        prefix = "Confirmation required"
        if subagent:
            prefix = f"Sub-agent [cyan]{subagent}[/cyan] needs approval"
        self.app._append_to_log(
            f"\n{risk_emoji} [bold yellow]{prefix}:[/bold yellow] "
            f"{event.tool_name} — {event.reason}"
        )

        self._stack.set_active("confirmation")
        modal = ConfirmationModal.from_confirmation_event(event)
        self.app.push_screen(modal, self.on_dismissed)

    def on_dismissed(self, result: str) -> None:
        self._stack.set_active(None)
        self.resolve(ConfirmationChoice(result))

    def resolve(self, choice: ConfirmationChoice) -> None:
        success = resolve_any_confirmation(getattr(self.app, "agent", None), choice)

        labels = {
            ConfirmationChoice.ALLOW_ONCE: "allowed (once)",
            ConfirmationChoice.ALLOW_SESSION: "allowed (this session)",
            ConfirmationChoice.ALLOW_ALWAYS: "allowed (always)",
            ConfirmationChoice.DENY: "denied",
        }

        if success:
            self.app._append_to_log(f"[dim]Confirmation {labels.get(choice, 'resolved')}.[/dim]")
        else:
            self.app._append_to_log("[yellow]Confirmation timed out or was already resolved.[/yellow]")

        self.app._pending_confirmation = None
        if hasattr(self.app, "_refresh_status_bar"):
            self.app._refresh_status_bar()
        elif hasattr(self.app, "set_status_line"):
            self.app.set_status_line("Ready")