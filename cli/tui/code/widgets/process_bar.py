"""Top bar: currently running background processes only."""

from __future__ import annotations

from textual import events
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

from cli.tui.shared.text_escape import escape_for_markup


def process_bar_row_markup(label: str) -> str:
    """Rich markup for one live process row (compound tags must close in order)."""
    safe = escape_for_markup(label)
    return (
        f"[green]🟢[/green] {safe}  [dim][underline]· click log · /process-stop[/underline][/dim]"
    )


class ProcessBarRow(Static):
    """One live process; click opens the log viewer."""

    def __init__(self, process_id: str, label: str, **kwargs) -> None:
        super().__init__(process_bar_row_markup(label), **kwargs)
        self.process_id = process_id
        self.add_class("process-bar-row")

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(CodeProcessBar.Pressed(self.process_id))


class CodeProcessBar(Vertical):
    class Pressed(Message):
        """Posted when the user clicks a running process row."""

        def __init__(self, process_id: str = "") -> None:
            super().__init__()
            self.process_id = process_id

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "process-bar")
        super().__init__(**kwargs)
        self.display = False
        self._process_ids: list[str] = []

    @property
    def process_ids(self) -> list[str]:
        return list(self._process_ids)

    def set_processes(self, items: list[tuple[str, str]]) -> None:
        """``items`` is ``[(process_id, label), ...]`` for processes that are alive."""
        alive = [
            (pid, label) for pid, label in items if (pid or "").strip() and (label or "").strip()
        ]
        self._process_ids = [pid for pid, _ in alive]
        try:
            self.remove_children()
        except Exception:
            pass
        if not alive:
            self.display = False
            self.remove_class("visible")
            return
        for process_id, label in alive:
            self.mount(ProcessBarRow(process_id, label))
        self.display = True
        self.add_class("visible")

    def set_process(self, label: str, *, healthy: bool = True, process_id: str = "") -> None:
        """Compat: one row, or hide if the process is not healthy/running."""
        if not healthy or not (label or "").strip():
            self.clear_process()
            return
        self.set_processes([(process_id or "proc", label)])

    def clear_process(self) -> None:
        self.set_processes([])
