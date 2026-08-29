"""Modal: answer a sub-agent ask_user question."""

from __future__ import annotations

import json
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from cli.tui.shared.text_escape import escape_for_markup


def _clip(text: str, max_len: int = 480) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 1] + "…"


class SubagentQuestionModal(ModalScreen[str | None]):
    """Show one sub-agent question and collect a free-text answer."""

    CSS = """
    SubagentQuestionModal {
        align: center middle;
    }

    #subq-dialog {
        background: $surface;
        border: thick $accent;
        padding: 1 2;
        width: 82;
        max-width: 94%;
        height: auto;
        max-height: 85%;
    }

    #subq-title {
        text-style: bold;
        color: $accent;
        text-align: center;
        margin-bottom: 1;
    }

    #subq-meta {
        color: $text-muted;
        margin-bottom: 1;
    }

    #subq-task {
        background: $surface-darken-1;
        padding: 0 1;
        margin-bottom: 1;
        max-height: 6;
        overflow-y: auto;
    }

    #subq-question {
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }

    #subq-context {
        color: $text-muted;
        padding: 0 1;
        margin-bottom: 1;
        max-height: 5;
        overflow-y: auto;
    }

    #subq-input {
        margin: 1 0;
        width: 100%;
    }

    #subq-buttons {
        align: center middle;
        height: auto;
        padding-top: 1;
    }

    #subq-buttons Button {
        margin: 0 1;
        min-width: 14;
    }

    #subq-queue {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    #subq-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Later", show=True),
    ]

    def __init__(
        self,
        *,
        request_id: str,
        subagent_name: str,
        question: str,
        context: str = "",
        task_preview: str = "",
        queue_index: int = 1,
        queue_total: int = 1,
        questions: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.subagent_name = subagent_name
        self.question = question
        self.context = context
        self.task_preview = task_preview
        self.queue_index = queue_index
        self.queue_total = queue_total
        self.questions = list(questions or [])
        self._option_map: dict[str, tuple[str, str]] = {}

    @classmethod
    def from_event(
        cls,
        event: object,
        *,
        task_preview: str = "",
        queue_index: int = 1,
        queue_total: int = 1,
    ) -> SubagentQuestionModal:
        return cls(
            request_id=str(getattr(event, "request_id", "") or ""),
            subagent_name=str(getattr(event, "subagent_name", "") or "sub-agent"),
            question=str(getattr(event, "question", "") or ""),
            context=str(getattr(event, "context", "") or ""),
            task_preview=task_preview,
            queue_index=queue_index,
            queue_total=queue_total,
            questions=list(getattr(event, "questions", None) or []),
        )

    def compose(self) -> ComposeResult:
        name = escape_for_markup(self.subagent_name or "sub-agent")
        rid = escape_for_markup(self.request_id or "—")
        q = _clip(self.question, 800) or "(empty question)"
        task = _clip(self.task_preview, 360)
        ctx = _clip(self.context, 360)

        with Container(id="subq-dialog"):
            yield Label("❓ Sub-agent needs your input", id="subq-title")
            if self.queue_total > 1:
                yield Static(
                    f"Question {self.queue_index} of {self.queue_total}",
                    id="subq-queue",
                )
            yield Static(
                f"From [cyan]{name}[/cyan]  ·  id [dim]{rid}[/dim]",
                id="subq-meta",
            )
            if task:
                yield Static(
                    f"[dim]Task[/dim]\n{escape_for_markup(task)}",
                    id="subq-task",
                    markup=True,
                )
            yield Static(q, id="subq-question", markup=False)
            if ctx:
                yield Static(
                    f"[dim]Context[/dim]\n{escape_for_markup(ctx)}",
                    id="subq-context",
                    markup=True,
                )
            options = self._first_options()
            if options:
                with Vertical(id="subq-options"):
                    for i, opt in enumerate(options):
                        bid = f"btn-opt-{i}"
                        qid = str((self.questions[0] or {}).get("id") or "q1")
                        self._option_map[bid] = (qid, str(opt.get("id") or ""))
                        label = str(opt.get("label") or opt.get("id") or "")[:48]
                        yield Button(label, id=bid, classes="subq-opt")
            yield Input(
                placeholder="Type your answer and press Enter…",
                id="subq-input",
            )
            with Horizontal(id="subq-buttons"):
                yield Button("Send answer", variant="success", id="btn-subq-send")
                yield Button("Skip / decide yourself", variant="default", id="btn-subq-skip")
            yield Static(
                "[dim]Enter = send · Esc = answer later · Skip = let sub-agent decide[/dim]",
                id="subq-hint",
            )

    def on_mount(self) -> None:
        try:
            self.query_one("#subq-input", Input).focus()
        except Exception:
            pass

    def _first_options(self) -> list[dict[str, Any]]:
        if not self.questions:
            return []
        opts = self.questions[0].get("options") if isinstance(self.questions[0], dict) else None
        return [o for o in (opts or []) if isinstance(o, dict)]

    def _submit(self, answer: str | None) -> None:
        self.dismiss(answer)

    @on(Button.Pressed, ".subq-opt")
    def on_option(self, event: Button.Pressed) -> None:
        bid = str(getattr(event.button, "id", "") or "")
        pair = self._option_map.get(bid)
        if not pair:
            return
        qid, oid = pair
        self._submit(json.dumps({qid: [oid]}, ensure_ascii=False))

    @on(Input.Submitted, "#subq-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        if text:
            self._submit(text)

    @on(Button.Pressed, "#btn-subq-send")
    def on_send(self) -> None:
        try:
            text = self.query_one("#subq-input", Input).value.strip()
        except Exception:
            text = ""
        if not text:
            self.notify("Enter an answer first", severity="warning")
            return
        self._submit(text)

    @on(Button.Pressed, "#btn-subq-skip")
    def on_skip(self) -> None:
        self._submit("")

    def action_cancel(self) -> None:
        self._submit(None)
