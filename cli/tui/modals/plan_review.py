"""In-chat plan review (no modal screen — Markdown in chat log)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.plan_review.clarification import parse_plan_review_response
from core.plan_review.review_events import PlanReviewRequestEvent
from core.plan_review.review_guard import PlanReviewChoice, get_plan_review_guard

if TYPE_CHECKING:
    from cli.tui.modals.stack import ModalStack


class PlanReviewPresenter:
    """Renders plan review in chat and resolves user text responses."""

    def __init__(self, app: Any, stack: ModalStack) -> None:
        self.app = app
        self._stack = stack
        self._guard_reference: Any | None = None
        self._pending_review_id: str | None = None
        self._phase: str = "approval"

    @property
    def is_awaiting(self) -> bool:
        return self._stack.active_kind == "plan_review"

    def show(self, event: PlanReviewRequestEvent) -> None:
        self._phase = getattr(event, "phase", "approval") or "approval"
        try:
            from rich.markdown import Markdown

            if event.rendered_markdown:
                self.app._append_to_log(Markdown(event.rendered_markdown))
            else:
                self.app._append_to_log(
                    f"\n[bold cyan]📋 Plan Review Required[/bold cyan] — "
                    f"{event.step_count} steps proposed.\n"
                )
        except Exception:
            self.app._append_to_log(
                f"\n[bold cyan]📋 Plan Review Required[/bold cyan] — "
                f"{event.step_count} steps proposed.\n"
            )

        if self._phase == "clarification":
            self.app._append_to_log(
                "\n[bold yellow]❓ Нужны уточнения перед планом[/bold yellow]\n"
                "[dim]Ответьте на вопросы выше. Можно «продолжай с допущениями», "
                "если хотите план без ответов, или «нет» для отмены.[/dim]\n"
            )
        else:
            complexity = ""
            analysis = getattr(event, "analysis", None) or {}
            if analysis:
                complexity = f" (complexity: {analysis.get('complexity', '?')})"

            self.app._append_to_log(
                f"\n[bold yellow]⚠ Подтверждаешь план?{complexity}[/bold yellow]\n"
                "[dim]Напиши '[bold]да[/bold]' для выполнения, '[bold]нет[/bold]' для отмены, "
                "или опиши что нужно изменить.[/dim]\n"
            )

        self._stack.set_active("plan_review")
        self._pending_review_id = event.review_id
        self._guard_reference = get_plan_review_guard()
        status = "Awaiting clarification" if self._phase == "clarification" else "Awaiting plan review"
        if hasattr(self.app, "set_status_line"):
            self.app.set_status_line(status)
        elif hasattr(self.app, "_set_status"):
            self.app._set_status(status, "yellow")

    def parse_response(self, text: str) -> tuple[PlanReviewChoice, str]:
        choice_value, feedback = parse_plan_review_response(text, phase=self._phase)
        return PlanReviewChoice(choice_value), feedback

    def handle_text_response(self, message: str) -> None:
        choice, feedback = self.parse_response(message)
        if self._phase == "clarification":
            labels = {
                PlanReviewChoice.REFINE: "📝 Ответы приняты — обновляю план",
                PlanReviewChoice.REJECT: "❌ Планирование отменено",
                PlanReviewChoice.PROCEED_ASSUMPTIONS: "⏭ Продолжаю с допущениями",
            }
        else:
            labels = {
                PlanReviewChoice.AUTO_EXECUTE: "✅ Подтверждено — выполняю план",
                PlanReviewChoice.REJECT: "❌ План отклонён",
                PlanReviewChoice.REFINE: "✏️ Уточняю план",
            }
        self.app._append_to_log(f"\n[bold]{labels.get(choice, 'Resolved')}[/bold]\n")
        if feedback and choice == PlanReviewChoice.REFINE:
            self.app._append_to_log(f"[dim]Feedback: {feedback[:200]}[/dim]\n")
        self.clear_awaiting()
        self.resolve(choice, feedback)

    def resolve(self, choice: PlanReviewChoice, feedback: str = "") -> None:
        if not self._guard_reference:
            self.app._append_to_log("[yellow]No PlanReviewGuard available.[/yellow]")
            return

        if not self._guard_reference._pending_reviews:
            self.app._append_to_log("[yellow]No pending plan review (may have timed out).[/yellow]")
            return

        review_id = list(self._guard_reference._pending_reviews.keys())[-1]
        success = self._guard_reference.resolve_review(review_id, choice, feedback)

        labels = {
            PlanReviewChoice.CONFIRM_STEP: "confirmed (step-by-step)",
            PlanReviewChoice.AUTO_EXECUTE: "auto-execute",
            PlanReviewChoice.REFINE: "refine plan",
            PlanReviewChoice.REJECT: "rejected",
            PlanReviewChoice.PROCEED_ASSUMPTIONS: "proceed with assumptions",
        }

        if success:
            self.app._append_to_log(f"[dim]Plan review {labels.get(choice, 'resolved')}.[/dim]")
            if choice == PlanReviewChoice.REJECT:
                self.app._execution_mode_index = 0
                self.app._append_to_log("[dim]Switched to ReAct mode. Use /mode to switch back.[/dim]")
        else:
            self.app._append_to_log("[yellow]Plan review timed out or was already resolved.[/yellow]")

        if hasattr(self.app, "_refresh_status_bar"):
            self.app._refresh_status_bar()
        elif hasattr(self.app, "set_status_line"):
            self.app.set_status_line("Ready")

    def cancel(self) -> None:
        if self.is_awaiting:
            self.resolve(PlanReviewChoice.REJECT)
        self.clear_awaiting()

    def clear_awaiting(self) -> None:
        self._stack.set_active(None)
        self._pending_review_id = None
        self._phase = "approval"