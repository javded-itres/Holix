"""Pending user prompts waiting for the agent, shown above the input."""

from __future__ import annotations

from dataclasses import dataclass

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Static


def format_queue_label(text: str, *, max_len: int = 88) -> str:
    one_line = " ".join((text or "").split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


@dataclass(slots=True)
class QueuedPrompt:
    item_id: str
    text: str


class PromptQueueRow(Horizontal):
    """One queued prompt: click text to edit, × to drop."""

    can_focus = False

    def __init__(self, item: QueuedPrompt, *, index: int, edit_label: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.item_id = item.item_id
        self._text = item.text
        self._index = index
        self._edit_label = edit_label
        self.add_class("queue-row")

    def compose(self) -> ComposeResult:
        label = format_queue_label(self._text)
        yield Static(
            f"[bold]{self._index}.[/bold] {label}",
            classes="queue-label",
        )
        yield Button(self._edit_label, classes="queue-edit", compact=True)
        yield Button("×", classes="queue-del", compact=True)

    def on_click(self, event: events.Click) -> None:
        widget = event.widget
        while widget is not None and widget is not self:
            if isinstance(widget, Button):
                return
            widget = widget.parent
        event.stop()
        self.post_message(PromptQueue.Edit(self.item_id))

    @on(Button.Pressed)
    def _on_button(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.has_class("queue-del"):
            self.post_message(PromptQueue.Remove(self.item_id))
            return
        self.post_message(PromptQueue.Edit(self.item_id))


class PromptQueue(Vertical):
    """Highlighted list of prompts that will run after the current turn."""

    class Edit(Message):
        def __init__(self, item_id: str) -> None:
            super().__init__()
            self.item_id = item_id

    class Remove(Message):
        def __init__(self, item_id: str) -> None:
            super().__init__()
            self.item_id = item_id

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "prompt-queue")
        super().__init__(**kwargs)
        self._items: list[QueuedPrompt] = []
        self.display = False

    @property
    def items(self) -> list[QueuedPrompt]:
        return list(self._items)

    def set_items(
        self,
        items: list[QueuedPrompt],
        *,
        title: str,
        hint: str,
        edit_label: str,
    ) -> None:
        self._items = list(items)
        try:
            header = self.query_one("#queue-header", Static)
            rows = self.query_one("#queue-rows", Vertical)
        except Exception:
            return
        header.update(f"[bold]{title}[/bold]  [dim]{hint}[/dim]" if self._items else "")
        rows.remove_children()
        if not self._items:
            self.display = False
            self.remove_class("visible")
            return
        for i, item in enumerate(self._items, start=1):
            rows.mount(PromptQueueRow(item, index=i, edit_label=edit_label))
        self.display = True
        self.add_class("visible")

    def compose(self) -> ComposeResult:
        yield Static("", id="queue-header")
        yield Vertical(id="queue-rows")
