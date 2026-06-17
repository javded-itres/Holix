"""Top bar showing a long-running background project process."""

from textual.widgets import Static


class CodeProcessBar(Static):
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
                f"[dim]· /process-stop to halt[/dim]"
            )
            self.remove_class("error")
        else:
            self.update(
                f"[red]🔴 Process error:[/red] {text}  "
                f"[dim]· fix & restart · /process-stop[/dim]"
            )
            self.add_class("error")
        self.display = True
        self.add_class("visible")

    def clear_process(self) -> None:
        self.update("")
        self.display = False
        self.remove_class("visible")
        self.remove_class("error")