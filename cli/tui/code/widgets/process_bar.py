"""Top bar showing a long-running background project process."""

from textual import events
from textual.message import Message
from textual.widgets import Static


class CodeProcessBar(Static):
    class Pressed(Message):
        """Posted when the user clicks the process bar."""

        def __init__(self) -> None:
            super().__init__()

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "process-bar")
        super().__init__("", **kwargs)
        self.display = False

    def set_process(self, label: str, *, healthy: bool = True) -> None:
        text = (label or "").strip()
        if not text:
            self.clear_process()
            return
        if healthy:
            self.update(
                f"[green]🟢 Process:[/green] {text}  "
                f"[dim underline]· click for output · /process-stop[/dim]"
            )
            self.remove_class("error")
        else:
            self.update(
                f"[red]🔴 Process error:[/red] {text}  "
                f"[dim underline]· click for log · /process-stop[/dim]"
            )
            self.add_class("error")
        self.display = True
        self.add_class("visible")
        self.add_class("clickable")

    def clear_process(self) -> None:
        self.update("")
        self.display = False
        self.remove_class("visible")
        self.remove_class("error")
        self.remove_class("clickable")

    def on_click(self, event: events.Click) -> None:
        if not self.display:
            return
        event.stop()
        self.post_message(self.Pressed())