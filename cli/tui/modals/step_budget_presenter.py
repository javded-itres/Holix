"""Step-budget Continue/Abort modal presenter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.agent_events import StepBudgetChoiceEvent
from core.runtime.step_budget_pause import (
    ABORT,
    CONTINUE,
    pending_ids,
    resolve_step_budget,
)

from cli.tui.modals.step_budget import StepBudgetModal

if TYPE_CHECKING:
    from cli.tui.modals.stack import ModalStack


class StepBudgetPresenter:
    """Shows StepBudgetModal and resolves the pause future."""

    def __init__(self, app: Any, stack: ModalStack) -> None:
        self.app = app
        self._stack = stack
        self._queue: list[StepBudgetChoiceEvent] = []
        self._active: StepBudgetChoiceEvent | None = None
        self._modal_open = False
        self._modal: StepBudgetModal | None = None

    def show(self, event: StepBudgetChoiceEvent) -> None:
        rid = (getattr(event, "request_id", None) or "").strip()
        if rid:
            if self._active and (self._active.request_id or "") == rid:
                return
            if any((e.request_id or "") == rid for e in self._queue):
                return
            if rid not in pending_ids():
                return
        self._queue.append(event)
        self._pump()

    def _log_request(self, event: StepBudgetChoiceEvent) -> None:
        write = getattr(self.app, "_append_to_log", None) or getattr(
            self.app, "transcript_write", None
        )
        if write:
            write(f"\n⚠ [bold yellow]{event.message or 'Step limit reached'}[/bold yellow]")

    def _release_active_ui(self, *, pop_screen: bool) -> None:
        self._modal_open = False
        self._active = None
        if self._stack.active_kind == "step_budget":
            self._stack.set_active(None)
        modal = self._modal
        self._modal = None
        if pop_screen and modal is not None and hasattr(self.app, "pop_screen"):
            try:
                self.app.pop_screen()
            except Exception:
                pass

    def _pump(self) -> None:
        if self._active is not None:
            rid = (self._active.request_id or "").strip()
            if rid and rid not in pending_ids():
                self._release_active_ui(pop_screen=True)
            else:
                return
        if self._modal_open:
            if self._active is None:
                self._modal_open = False
            else:
                return
        if not self._queue:
            return
        if self._stack.has_active and self._stack.active_kind not in (None, "step_budget"):
            if hasattr(self.app, "set_timer"):
                self.app.set_timer(0.35, self._pump)
            return

        event = self._queue.pop(0)
        rid = (event.request_id or "").strip()
        if rid and rid not in pending_ids():
            self._pump()
            return
        self._active = event
        self.app._pending_step_budget = event
        self._log_request(event)
        self._open_modal(event)

    def _open_modal(self, event: StepBudgetChoiceEvent) -> None:
        self._stack.set_active("step_budget")
        modal = StepBudgetModal(
            message=event.message or "Step limit reached",
            request_id=event.request_id,
            extra_steps=int(event.extra_steps or 30),
        )
        self._modal = modal
        self._modal_open = True

        def _open() -> None:
            try:
                self.app.push_screen(modal, self.on_dismissed)
            except Exception:
                self._modal = None
                self._modal_open = False
                self._active = None
                if self._stack.active_kind == "step_budget":
                    self._stack.set_active(None)

        if hasattr(self.app, "call_later"):
            self.app.call_later(_open)
        else:
            _open()

    def on_dismissed(self, result: str | None) -> None:
        self._modal_open = False
        self._modal = None
        self._stack.set_active(None)
        event = self._active
        self._active = None
        raw = (result if isinstance(result, str) else None) or ABORT
        choice = CONTINUE if str(raw).strip().lower() == CONTINUE else ABORT
        rid = getattr(event, "request_id", None) if event else None
        resolve_step_budget(str(rid or ""), choice)
        write = getattr(self.app, "_append_to_log", None) or getattr(
            self.app, "transcript_write", None
        )
        if write:
            if choice == CONTINUE:
                write("[dim]Step budget: continue[/dim]")
            else:
                write("[dim]Step budget: abort[/dim]")
        self.app._pending_step_budget = None
        self._pump()
