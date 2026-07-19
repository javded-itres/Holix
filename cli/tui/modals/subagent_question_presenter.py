"""Presenter: queue + modal for sub-agent ask_user questions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.subagents.interaction import get_interaction_bridge
from core.subagents.interaction_events import SubAgentQuestionEvent

from cli.tui.modals.subagent_question import SubagentQuestionModal

if TYPE_CHECKING:
    from cli.tui.modals.stack import ModalStack


class SubagentQuestionPresenter:
    """Shows sub-agent questions one at a time with a clear answer UI."""

    def __init__(self, app: Any, stack: ModalStack) -> None:
        self.app = app
        self._stack = stack
        self._queue: list[SubAgentQuestionEvent] = []
        self._active: SubAgentQuestionEvent | None = None
        self._modal_open = False

    @property
    def pending_count(self) -> int:
        n = len(self._queue)
        if self._active is not None:
            n += 1
        return n

    def show(self, event: SubAgentQuestionEvent) -> None:
        """Enqueue a question and open the modal if idle."""
        rid = (event.request_id or "").strip()
        if rid and any((e.request_id or "") == rid for e in self._queue):
            return
        if self._active and (self._active.request_id or "") == rid:
            return

        self._queue.append(event)
        self._log_event(event)
        self._pump()

    def sync_with_bridge(self) -> None:
        """Drop queue items already answered outside the modal (free text / slash)."""
        bridge = get_interaction_bridge(getattr(self.app, "agent", None))
        live_ids = set(bridge.pending_question_ids) if bridge else set()

        def _still_pending(ev: SubAgentQuestionEvent) -> bool:
            rid = (ev.request_id or "").strip()
            if not rid:
                return True
            if bridge is None:
                return True
            return rid in live_ids

        self._queue = [e for e in self._queue if _still_pending(e)]
        if self._active is not None and not _still_pending(self._active):
            # External resolve while modal may still be open — leave dismiss to user
            # or clear active if modal already closed.
            if not self._modal_open:
                self._active = None

    def _task_preview_for(self, subagent_name: str) -> str:
        agent = getattr(self.app, "agent", None)
        subagents = getattr(agent, "subagents", None) if agent else None
        if subagents is None:
            return ""
        handle = None
        try:
            handle = subagents.get_handle(subagent_name)
        except Exception:
            handle = None
        if handle is None:
            return ""
        return (getattr(handle, "task_preview", None) or "").strip()

    def _log_event(self, event: SubAgentQuestionEvent) -> None:
        name = event.subagent_name or "sub-agent"
        q = (event.question or "").strip() or "(empty question)"
        task = self._task_preview_for(name)
        lines = [
            f"\n[bold magenta]❓ Sub-agent question[/bold magenta]  "
            f"[cyan]{name}[/cyan]  [dim]{event.request_id}[/dim]",
        ]
        if task:
            preview = task if len(task) <= 200 else task[:199] + "…"
            lines.append(f"[dim]Task:[/dim] {preview}")
        lines.append(f"[bold]{q}[/bold]")
        if (event.context or "").strip():
            ctx = event.context.strip()
            if len(ctx) > 200:
                ctx = ctx[:199] + "…"
            lines.append(f"[dim]Context:[/dim] {ctx}")
        remaining = max(0, self.pending_count - 1)
        if remaining:
            lines.append(f"[dim]+{remaining} more waiting[/dim]")
        lines.append(
            "[dim]Answer in the dialog, or type free text if only one question is open, "
            f"or /subagent-reply {name} …[/dim]\n"
        )
        write = getattr(self.app, "transcript_write", None) or getattr(
            self.app, "_append_to_log", None
        )
        if write:
            write("\n".join(lines))

    def _pump(self) -> None:
        if self._modal_open or self._active is not None:
            return
        if not self._queue:
            return
        if self._stack.has_active and self._stack.active_kind not in (None, "subagent_question"):
            # Another modal (confirmation/plan) is open — retry shortly
            if hasattr(self.app, "set_timer"):
                self.app.set_timer(0.35, self._pump)
            return

        event = self._queue.pop(0)
        if not self._still_pending_on_bridge(event):
            self._pump()
            return
        self._active = event
        self._open_modal(event)

    def _still_pending_on_bridge(self, event: SubAgentQuestionEvent) -> bool:
        rid = (event.request_id or "").strip()
        if not rid:
            return True
        bridge = get_interaction_bridge(getattr(self.app, "agent", None))
        if bridge is None:
            return True
        return rid in bridge.pending_question_ids

    def _open_modal(self, event: SubAgentQuestionEvent) -> None:
        task = self._task_preview_for(event.subagent_name or "")
        total = self.pending_count  # includes active
        modal = SubagentQuestionModal.from_event(
            event,
            task_preview=task,
            queue_index=1,
            queue_total=max(1, total),
        )
        self._stack.set_active("subagent_question")
        self._modal_open = True

        def _open() -> None:
            try:
                self.app.push_screen(modal, self.on_dismissed)
            except Exception:
                self._modal_open = False
                self._active = None
                write = getattr(self.app, "transcript_write", None)
                if write:
                    write(
                        "[yellow]Question dialog unavailable — answer with "
                        f"/subagent-reply {event.subagent_name} <text>[/yellow]"
                    )
                self._pump()

        if hasattr(self.app, "call_later"):
            self.app.call_later(_open)
        else:
            _open()

    def on_dismissed(self, result: str | None) -> None:
        self._modal_open = False
        self._stack.set_active(None)
        event = self._active
        self._active = None

        if event is None:
            self._pump()
            return

        name = event.subagent_name or "sub-agent"
        rid = event.request_id or ""
        write = getattr(self.app, "transcript_write", None)

        if result is None:
            # Esc — leave bridge pending; answer later via free text / slash
            if write:
                write(
                    f"[dim]Dismissed dialog for {name} — still waiting. "
                    f"Answer with free text (if alone) or /subagent-reply {name} …[/dim]"
                )
            if hasattr(self.app, "_refresh_status_bar"):
                self.app._refresh_status_bar()
            self._pump()
            return

        answer = (result or "").strip()
        if not answer:
            answer = "(user skipped — proceed with best judgment)"

        ok = self._resolve(event, answer)
        if write:
            if ok:
                preview = answer if len(answer) <= 120 else answer[:119] + "…"
                write(f"[green]✓ replied to {name}:[/green] {preview}")
            else:
                write(
                    f"[yellow]Could not deliver answer to {name} "
                    f"(id={rid}) — already resolved?[/yellow]"
                )

        if hasattr(self.app, "_refresh_status_bar"):
            self.app._refresh_status_bar()
        self._pump()

    def _resolve(self, event: SubAgentQuestionEvent, answer: str) -> bool:
        agent = getattr(self.app, "agent", None)
        bridge = get_interaction_bridge(agent)
        if bridge is None:
            return False
        rid = (event.request_id or "").strip()
        if rid and bridge.resolve_question(rid, answer):
            return True
        name = (event.subagent_name or "").strip()
        if name and bridge.resolve_question_for_subagent(name, answer):
            return True
        return bridge.resolve_single_pending_question(answer)
