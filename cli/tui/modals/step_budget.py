"""Step-budget Continue / Abort modal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class StepBudgetModal(ModalScreen):
    """Two-button pause when the main agent hits max_steps."""

    CSS = """
    StepBudgetModal {
        align: center middle;
    }

    #step-budget-dialog {
        background: $surface;
        border: thick $warning;
        padding: 1 2;
        width: 68;
        max-width: 90%;
        height: auto;
        max-height: 80%;
    }

    #step-budget-title {
        text-align: center;
        padding: 0 1;
        margin-bottom: 1;
    }

    #step-budget-body {
        padding: 0 1;
        margin-bottom: 1;
    }

    #step-budget-buttons {
        align: center middle;
        height: auto;
        padding: 1;
    }

    #step-budget-buttons Button {
        margin: 0 1;
        min-width: 16;
    }
    """

    def __init__(
        self,
        message: str,
        request_id: str = "",
        extra_steps: int = 30,
    ):
        super().__init__()
        self.message = message
        self.request_id = request_id
        self.extra_steps = extra_steps

    def compose(self) -> ComposeResult:
        with Container(id="step-budget-dialog"):
            yield Label("⚠ Step limit reached", id="step-budget-title")
            yield Static(self.message, id="step-budget-body", markup=False)
            with Horizontal(id="step-budget-buttons"):
                yield Button(
                    f"[1] Continue (+{self.extra_steps})",
                    variant="success",
                    id="btn-continue",
                )
                yield Button("[2] Abort", variant="error", id="btn-abort")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-continue":
            self.dismiss("continue")
            return
        self.dismiss("abort")

    def on_key(self, event) -> None:
        if event.key == "1":
            event.stop()
            self.dismiss("continue")
        elif event.key in {"2", "escape"}:
            event.stop()
            self.dismiss("abort")
