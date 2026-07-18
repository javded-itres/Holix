"""Confirmation flow: modal queue + ActionGuard resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.security.confirmation import ConfirmationChoice, get_action_guard
from core.security.confirmation_events import ConfirmationRequestEvent
from core.subagents.interaction import resolve_any_confirmation

from cli.tui.modals.confirmation import ConfirmationModal

if TYPE_CHECKING:
    from cli.tui.modals.stack import ModalStack


class ConfirmationPresenter:
    """Shows ConfirmationModal one-at-a-time and resolves ActionGuard futures."""

    def __init__(self, app: Any, stack: ModalStack) -> None:
        self.app = app
        self._stack = stack
        self._queue: list[ConfirmationRequestEvent] = []
        self._active: ConfirmationRequestEvent | None = None
        self._modal_open = False

    def _resolve_guard_reference(self) -> None:
        agent = getattr(self.app, "agent", None)
        if agent and hasattr(agent, "tools") and agent.tools._action_guard:
            self.app._action_guard_reference = agent.tools._action_guard
        else:
            self.app._action_guard_reference = get_action_guard()

    def show(self, event: ConfirmationRequestEvent) -> None:
        """Enqueue a confirmation and open the modal if idle."""
        self._resolve_guard_reference()

        cid = (getattr(event, "confirmation_id", None) or "").strip()
        if cid:
            if self._active and (self._active.confirmation_id or "") == cid:
                return
            if any((e.confirmation_id or "") == cid for e in self._queue):
                return
            # Already resolved (e.g. session grant unblocked siblings)
            if not self._is_still_pending(cid):
                return

        self._queue.append(event)
        self._pump()

    def _is_still_pending(self, confirmation_id: str) -> bool:
        if not confirmation_id:
            return True
        guard = getattr(self.app, "_action_guard_reference", None)
        if guard is None:
            agent = getattr(self.app, "agent", None)
            if agent and getattr(agent, "tools", None):
                guard = getattr(agent.tools, "_action_guard", None)
        if guard is None:
            guard = get_action_guard()
        if guard is None:
            return True
        return confirmation_id in guard._pending_confirmations

    def _log_request(self, event: ConfirmationRequestEvent) -> None:
        risk_emoji = {"no": "🟢", "low": "🔵", "medium": "🟡", "high": "🔴"}.get(
            event.risk_level, "⚠"
        )
        subagent = getattr(event, "subagent_name", "") or ""
        prefix = "Confirmation required"
        if subagent:
            prefix = f"Sub-agent [cyan]{subagent}[/cyan] needs approval"
        remaining = max(0, len(self._queue))
        extra = f"  [dim]+{remaining} more queued[/dim]" if remaining else ""
        write = getattr(self.app, "_append_to_log", None) or getattr(
            self.app, "transcript_write", None
        )
        if write:
            write(
                f"\n{risk_emoji} [bold yellow]{prefix}:[/bold yellow] "
                f"{event.tool_name} — {event.reason}{extra}"
            )

    def _pump(self) -> None:
        if self._modal_open or self._active is not None:
            return
        if not self._queue:
            return
        if self._stack.has_active and self._stack.active_kind not in (None, "confirmation"):
            # Another overlay is open — retry shortly
            if hasattr(self.app, "set_timer"):
                self.app.set_timer(0.35, self._pump)
            return

        event = self._queue.pop(0)
        cid = (event.confirmation_id or "").strip()
        if cid and not self._is_still_pending(cid):
            self._pump()
            return
        self._active = event
        self.app._pending_confirmation = event
        self._log_request(event)
        self._open_modal(event)

    def _open_modal(self, event: ConfirmationRequestEvent) -> None:
        self._stack.set_active("confirmation")
        modal = ConfirmationModal.from_confirmation_event(event)
        self._modal_open = True

        def _open() -> None:
            try:
                self.app.push_screen(modal, self.on_dismissed)
            except Exception:
                self._modal_open = False
                self._active = None
                write = getattr(self.app, "_append_to_log", None) or getattr(
                    self.app, "transcript_write", None
                )
                if write:
                    write(
                        "[yellow]Confirmation modal unavailable — "
                        "use /1 /2 /3 /4 in the prompt[/yellow]"
                    )
                # Fall back: leave future pending so slash commands work
                self._pump()

        # Textual: call_later(callback, *args) — not call_later(delay, callback).
        if hasattr(self.app, "call_later"):
            self.app.call_later(_open)
        else:
            _open()

    def on_dismissed(self, result: str | None) -> None:
        self._modal_open = False
        self._stack.set_active(None)
        event = self._active
        self._active = None

        raw = (result if isinstance(result, str) else None) or "deny"
        try:
            choice = ConfirmationChoice(raw)
        except ValueError:
            choice = ConfirmationChoice.DENY

        self.resolve(choice, confirmation_id=getattr(event, "confirmation_id", None) if event else None)
        self._pump()

        # After confirmation stack clears, surface any queued sub-agent questions
        sq = getattr(self._stack, "subagent_question", None)
        if sq is not None and hasattr(sq, "_pump"):
            try:
                sq._pump()
            except Exception:
                pass

    def resolve(
        self,
        choice: ConfirmationChoice,
        *,
        confirmation_id: str | None = None,
    ) -> None:
        event = getattr(self.app, "_pending_confirmation", None)
        cid = (confirmation_id or "").strip() or None
        if cid is None and event is not None:
            cid = (getattr(event, "confirmation_id", None) or "").strip() or None

        success = resolve_any_confirmation(
            getattr(self.app, "agent", None),
            choice,
            confirmation_id=cid,
        )

        labels = {
            ConfirmationChoice.ALLOW_ONCE: "allowed (once)",
            ConfirmationChoice.ALLOW_SESSION: "allowed (this session)",
            ConfirmationChoice.ALLOW_ALWAYS: "allowed (always)",
            ConfirmationChoice.DENY: "denied",
        }

        write = getattr(self.app, "_append_to_log", None) or getattr(
            self.app, "transcript_write", None
        )
        if write:
            if success:
                write(f"[dim]Confirmation {labels.get(choice, 'resolved')}.[/dim]")
            else:
                write(
                    "[yellow]Confirmation timed out or was already resolved.[/yellow]"
                )

        # Drop matching queue entries already resolved via session grant wake-up
        if success and choice in (
            ConfirmationChoice.ALLOW_SESSION,
            ConfirmationChoice.ALLOW_ALWAYS,
        ):
            self._drop_resolved_from_queue()

        if event is not None and (
            not cid or (getattr(event, "confirmation_id", None) or "") == cid
        ):
            self.app._pending_confirmation = None

        if hasattr(self.app, "_refresh_status_bar"):
            self.app._refresh_status_bar()
        elif hasattr(self.app, "set_status_line"):
            self.app.set_status_line("Ready")

    def _drop_resolved_from_queue(self) -> None:
        """Remove queued events whose futures are already gone (auto-resolved)."""
        agent = getattr(self.app, "agent", None)
        guard = None
        if agent and getattr(agent, "tools", None):
            guard = getattr(agent.tools, "_action_guard", None)
        if guard is None:
            guard = get_action_guard()
        if guard is None:
            return
        live = set(guard._pending_confirmations.keys())
        self._queue = [
            e for e in self._queue if (e.confirmation_id or "") in live or not e.confirmation_id
        ]
