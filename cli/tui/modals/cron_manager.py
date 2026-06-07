"""TUI modal: list cron rules, enable/disable, delete."""

from __future__ import annotations

from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static

from core.cron.store import CronStore


class CronManagerScreen(ModalScreen[None]):
    """Manage cron jobs for the active profile."""

    DEFAULT_CSS = """
    CronManagerScreen {
        align: center middle;
    }
    #cron-panel {
        width: 88%;
        max-width: 100;
        height: 75%;
        border: solid $primary;
        background: $surface;
        padding: 0 1 1 1;
    }
    #cron-list {
        height: 1fr;
        border: solid $primary-darken-2;
        margin: 1 0;
    }
    #cron-detail {
        height: auto;
        max-height: 8;
        padding: 0 1;
        color: $text-muted;
    }
    #cron-actions {
        height: auto;
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close", show=False),
    ]

    def __init__(self, profile: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._profile = profile
        self._store = CronStore(profile)
        self._selected_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="cron-panel"):
            yield Header(show_clock=False)
            yield Static(
                "[bold]Cron rules[/bold]  [dim]gateway scheduler · profile "
                f"{self._profile}[/dim]",
                id="cron-title",
            )
            yield ListView(id="cron-list")
            yield Static("Select a job", id="cron-detail")
            with Horizontal(id="cron-actions"):
                yield Button("Enable", id="btn-cron-on", variant="success")
                yield Button("Disable", id="btn-cron-off")
                yield Button("Delete", id="btn-cron-del", variant="error")
                yield Button("Refresh", id="btn-cron-refresh")
                yield Button("Close", id="btn-cron-close")
            yield Footer()

    def on_mount(self) -> None:
        self._reload_list()

    def _reload_list(self) -> None:
        lv = self.query_one("#cron-list", ListView)
        lv.clear()
        jobs = self._store.list_jobs()
        if not jobs:
            lv.mount(ListItem(Static("[dim]No cron jobs — use /cron add …[/dim]")))
            self.query_one("#cron-detail", Static).update(
                "[dim]/cron add every day at 9 :: your task[/dim]"
            )
            self._selected_id = None
            return
        for job in jobs:
            flag = "●" if job.enabled else "○"
            label = (
                f"{flag} [cyan]{job.id}[/cyan]  {job.name or job.task[:36]}\n"
                f"   [dim]{job.cron_expression}[/dim]  next {(job.next_run_at or '—')[:16]}"
            )
            item = ListItem(Static(label), id=f"cron-item-{job.id}")
            item._job_id = job.id  # type: ignore[attr-defined]
            lv.mount(item)
        if self._selected_id:
            self._restore_list_index(lv, self._selected_id)
        elif lv.children:
            lv.index = 0
            first = lv.children[0]
            jid = getattr(first, "_job_id", None)
            if jid:
                self._selected_id = jid

    def _restore_list_index(self, lv: ListView, job_id: str) -> None:
        target_id = f"cron-item-{job_id}"
        for i, child in enumerate(lv.children):
            if child.id == target_id:
                lv.index = i
                return

    def _list_item_at_index(self, lv: ListView) -> ListItem | None:
        if lv.index is None:
            return None
        children = list(lv.children)
        if 0 <= lv.index < len(children):
            child = children[lv.index]
            if isinstance(child, ListItem):
                return child
        return None

    def _job_id_from_item(self, item: ListItem | None) -> str | None:
        if item is None:
            return None
        jid = getattr(item, "_job_id", None)
        if jid:
            return str(jid)
        if item.id and item.id.startswith("cron-item-"):
            return item.id.replace("cron-item-", "", 1)
        return None

    def _job_from_selection(self):
        if self._selected_id:
            job = self._store.get(self._selected_id)
            if job is not None:
                return job
        lv = self.query_one("#cron-list", ListView)
        jid = self._job_id_from_item(self._list_item_at_index(lv))
        if not jid:
            return None
        return self._store.get(jid)

    @on(ListView.Selected)
    def _on_select(self, event: ListView.Selected) -> None:
        job = None
        jid = getattr(event.item, "_job_id", None)
        if jid:
            job = self._store.get(jid)
        if job is None:
            job = self._job_from_selection()
        if job is None:
            return
        self._selected_id = job.id
        try:
            self._restore_list_index(self.query_one("#cron-list", ListView), job.id)
        except Exception:
            pass
        detail = self.query_one("#cron-detail", Static)
        lines = [
            f"[bold]{job.name}[/bold]",
            f"Task: {job.task[:120]}{'…' if len(job.task) > 120 else ''}",
            f"Status: {job.last_status or '—'} · runs: {job.run_count}",
            f"Log session: [cyan]{job.conversation_id()}[/cyan]",
        ]
        if getattr(job, "session_id", None):
            lines.append(f"Summary → [cyan]{job.session_id}[/cyan]")
        if getattr(job, "last_result", None):
            preview = job.last_result.replace("\n", " ")[:200]
            lines.append(f"Last result: [dim]{preview}{'…' if len(job.last_result) > 200 else ''}[/dim]")
        detail.update("\n".join(lines))

    @work(exclusive=True)
    async def _toggle(self, enabled: bool) -> None:
        job = self._job_from_selection()
        if job is None:
            self.app.notify("Select a job first")
            return
        self._store.set_enabled(job.id, enabled)
        self._selected_id = job.id
        self._reload_list()
        self.app.notify(f"{'Enabled' if enabled else 'Disabled'} {job.id}")

    @work(exclusive=True)
    async def _delete(self) -> None:
        job = self._job_from_selection()
        if job is None:
            self.app.notify("Select a job first")
            return
        self._store.remove(job.id)
        self._selected_id = None
        self._reload_list()
        self.app.notify(f"Removed {job.id}")

    @on(Button.Pressed, "#btn-cron-on")
    def _on_enable(self) -> None:
        self._toggle(True)

    @on(Button.Pressed, "#btn-cron-off")
    def _on_disable(self) -> None:
        self._toggle(False)

    @on(Button.Pressed, "#btn-cron-del")
    def _on_delete(self) -> None:
        self._delete()

    @on(Button.Pressed, "#btn-cron-refresh")
    def _on_refresh(self) -> None:
        self._store.refresh_all_next_runs()
        self._reload_list()

    @on(Button.Pressed, "#btn-cron-close")
    def _on_close(self) -> None:
        self.dismiss(None)


def open_cron_manager(host: Any, profile: str) -> None:
    host.push_screen(CronManagerScreen(profile))