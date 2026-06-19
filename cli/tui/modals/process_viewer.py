"""TUI modal: background process log output and kill."""

from __future__ import annotations

from typing import Any

from core.i18n import host_locale, t
from core.runtime.background_process import BackgroundProcessRecord
from core.runtime.background_process_health import tail_log_file
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Static, TextArea


def resolve_background_process_record(
    host: Any,
    *,
    process_id: str | None = None,
) -> BackgroundProcessRecord | None:
    from core.runtime.background_process import get_background_process_registry

    registry = get_background_process_registry()
    profile = str(getattr(host, "profile", None) or "default")
    conversation_id = str(getattr(host, "conversation_id", None) or "default")

    pid = (process_id or getattr(host, "_background_process_id", None) or "").strip()
    if pid:
        rec = registry.get(pid)
        if rec is not None:
            return rec

    rec = registry.active_for_scope(profile=profile, conversation_id=conversation_id)
    if rec is not None:
        return rec

    records = registry.list_for_scope(profile=profile, conversation_id=conversation_id)
    return records[0] if records else None


def format_process_log_text(rec: BackgroundProcessRecord | None, *, lang: str) -> str:
    if rec is None:
        return t("tui.process.not_found", lang)

    if rec.log_path:
        log = tail_log_file(rec.log_path)
        if log.strip():
            return log

    if rec.is_running():
        return t("tui.process.output_waiting", lang)
    return t("tui.process.output_empty", lang)


def format_process_meta(rec: BackgroundProcessRecord | None, *, lang: str) -> str:
    if rec is None:
        return t("tui.process.not_found", lang)

    status = (
        t("tui.process.status_running", lang)
        if rec.is_running()
        else t("tui.process.status_stopped", lang)
    )
    return (
        f"[bold]{rec.label}[/bold]  "
        f"[dim]pid {rec.pid} · {status} · {rec.process_id}[/dim]\n"
        f"[dim]{t('tui.process.command', lang)}:[/dim] {rec.command}"
    )


class BackgroundProcessViewerScreen(ModalScreen[None]):
    """Show tail of the session background process log; allow kill."""

    DEFAULT_CSS = """
    BackgroundProcessViewerScreen {
        align: center middle;
    }
    #process-panel {
        width: 92%;
        height: 82%;
        border: solid $primary;
        background: $surface;
        padding: 0 1 1 1;
    }
    #process-meta {
        height: auto;
        max-height: 4;
        padding: 0 1;
    }
    #process-hint {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: dim;
    }
    #process-log {
        height: 1fr;
        margin: 1 0;
    }
    #process-actions {
        height: auto;
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close", show=False),
    ]

    def __init__(self, host: Any, *, process_id: str | None = None) -> None:
        super().__init__()
        self._host = host
        self._process_id = (process_id or "").strip() or None
        self._lang = host_locale(host)
        self._record: BackgroundProcessRecord | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="process-panel"):
            yield Header(show_clock=False)
            yield Static("", id="process-meta")
            yield Static("", id="process-hint")
            yield TextArea("", id="process-log", read_only=True, show_line_numbers=True)
            with Horizontal(id="process-actions"):
                yield Button("", id="btn-process-refresh")
                yield Button("", id="btn-process-kill", variant="error")
                yield Button("", id="btn-process-close")
            yield Footer()

    def on_mount(self) -> None:
        self.title = t("tui.process.title", self._lang)
        self.query_one("#btn-process-refresh", Button).label = t(
            "tui.process.refresh", self._lang
        )
        self.query_one("#btn-process-kill", Button).label = t(
            "tui.process.kill", self._lang
        )
        self.query_one("#btn-process-close", Button).label = t(
            "tui.process.close", self._lang
        )
        self.query_one("#process-hint", Static).update(
            t("tui.process.hint", self._lang)
        )
        self._reload()

    def _reload(self) -> None:
        self._record = resolve_background_process_record(
            self._host,
            process_id=self._process_id,
        )
        self.query_one("#process-meta", Static).update(
            format_process_meta(self._record, lang=self._lang)
        )
        log = format_process_log_text(self._record, lang=self._lang)
        self.query_one("#process-log", TextArea).text = log

        kill_btn = self.query_one("#btn-process-kill", Button)
        kill_btn.disabled = self._record is None or not self._record.is_running()

    @work(exclusive=True)
    async def _kill_process(self) -> None:
        from core.runtime.background_process import get_background_process_registry

        rec = self._record or resolve_background_process_record(
            self._host,
            process_id=self._process_id,
        )
        if rec is None:
            self.app.notify(t("tui.process.not_found", self._lang))
            return
        if not rec.is_running():
            self.app.notify(t("tui.process.already_stopped", self._lang))
            self._reload()
            return

        registry = get_background_process_registry()
        stopped = await registry.stop(rec.process_id)
        if stopped is None:
            self.app.notify(t("tui.process.not_found", self._lang))
            return

        host = self._host
        if hasattr(host, "clear_background_process"):
            host.clear_background_process()
        if hasattr(host, "sync_background_process_bar"):
            host.sync_background_process_bar()
        if hasattr(host, "transcript_write"):
            host.transcript_write(
                t(
                    "tui.process.killed",
                    self._lang,
                    label=stopped.label,
                    pid=stopped.pid,
                )
            )

        self.app.notify(
            t("tui.process.killed_short", self._lang, label=stopped.label)
        )
        self._reload()

    @on(Button.Pressed, "#btn-process-refresh")
    def _on_refresh(self) -> None:
        self._reload()

    @on(Button.Pressed, "#btn-process-kill")
    def _on_kill(self) -> None:
        self._kill_process()

    @on(Button.Pressed, "#btn-process-close")
    def _on_close(self) -> None:
        self.dismiss(None)


def open_background_process_viewer(host: Any, *, process_id: str | None = None) -> None:
    if not hasattr(host, "push_screen"):
        raise RuntimeError("Process viewer requires TUI (push_screen)")
    host.push_screen(
        BackgroundProcessViewerScreen(host, process_id=process_id),
    )