"""TUI modal: assign / unassign external CLIs to sub-agents."""

from __future__ import annotations

from typing import Any, Literal

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static

from core.external_cli.assignment import (
    assign_cli_to_subagent,
    list_cli_assignment_rows,
    subagent_type_choices,
    unassign_cli_subagent,
)
from core.external_cli.platform import launch_supported
from core.i18n import host_locale, t


def _resolve_binary(spec) -> str | None:
    from cli.launch.setup_wizard import _binary_installed

    return _binary_installed(spec)


class LaunchManagerScreen(ModalScreen[None]):
    """Manage external CLI → sub-agent assignments for the active profile."""

    DEFAULT_CSS = """
    LaunchManagerScreen {
        align: center middle;
    }
    #launch-panel {
        width: 92%;
        max-width: 110;
        height: 78%;
        border: solid $primary;
        background: $surface;
        padding: 0 1 1 1;
    }
    #launch-list {
        height: 1fr;
        border: solid $primary-darken-2;
        margin: 1 0;
    }
    #launch-detail {
        height: auto;
        max-height: 10;
        padding: 0 1;
        color: $text-muted;
    }
    #launch-actions {
        height: auto;
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("escape", "back_or_close", "Back"),
        Binding("q", "back_or_close", "Back", show=False),
    ]

    def __init__(self, host: Any) -> None:
        super().__init__()
        self._host = host
        self._profile = str(getattr(host, "profile", None) or "default")
        self._lang = host_locale(host)
        self._view: Literal["clis", "assign"] = "clis"
        self._selected_cli_id: str | None = None
        self._assign_cli_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="launch-panel"):
            yield Header(show_clock=False)
            yield Static("", id="launch-title")
            yield Static("", id="launch-hint")
            yield ListView(id="launch-list")
            yield Static("", id="launch-detail")
            with Horizontal(id="launch-actions"):
                yield Button("", id="btn-launch-assign", variant="success")
                yield Button("", id="btn-launch-unassign")
                yield Button("", id="btn-launch-refresh")
                yield Button("", id="btn-launch-close")
            yield Footer()

    def on_mount(self) -> None:
        self.title = t("tui.launch.title", self._lang)
        self._apply_labels()
        self._render_list()

    def _apply_labels(self) -> None:
        self.query_one("#btn-launch-assign", Button).label = t(
            "tui.launch.assign", self._lang
        )
        self.query_one("#btn-launch-unassign", Button).label = t(
            "tui.launch.unassign", self._lang
        )
        self.query_one("#btn-launch-refresh", Button).label = t(
            "tui.launch.refresh", self._lang
        )
        self.query_one("#btn-launch-close", Button).label = t(
            "tui.launch.close", self._lang
        )

    def _rows(self):
        return list_cli_assignment_rows(self._profile, resolve_binary=_resolve_binary)

    def _render_list(self) -> None:
        title = self.query_one("#launch-title", Static)
        hint = self.query_one("#launch-hint", Static)
        lv = self.query_one("#launch-list", ListView)
        lv.clear()

        if self._view == "assign":
            title.update(
                f"[bold]{t('tui.launch.pick_subagent', self._lang)}[/bold]  "
                f"[dim]{self._assign_cli_id or ''}[/dim]"
            )
            hint.update(f"[dim]{t('tui.launch.pick_hint', self._lang)}[/dim]")
            for agent_id, desc in subagent_type_choices(profile=self._profile):
                item = ListItem(
                    Static(
                        f"[cyan]{agent_id}[/cyan]  [dim]{desc[:72]}[/dim]"
                    )
                )
                item._pick_kind = "subagent"  # type: ignore[attr-defined]
                item._agent_type = agent_id  # type: ignore[attr-defined]
                lv.mount(item)
            self._update_detail(None)
            self._sync_action_buttons(assigning=True)
            return

        title.update(
            f"[bold]{t('tui.launch.title', self._lang)}[/bold]  "
            f"[dim]{self._profile}[/dim]"
        )
        hint.update(f"[dim]{t('tui.launch.list_hint', self._lang)}[/dim]")
        rows = self._rows()
        if not rows:
            lv.mount(
                ListItem(
                    Static(f"[dim]{t('tui.launch.empty', self._lang)}[/dim]")
                )
            )
            self._update_detail(None)
            self._sync_action_buttons(assigning=False)
            return

        for row in rows:
            mark = "●" if row.assigned else "○"
            sub = row.agent_slot if row.assigned else "—"
            bin_mark = "✓" if row.binary else "✗"
            label = (
                f"{mark} [cyan]{row.cli_id}[/cyan]  {row.display_name}\n"
                f"   [dim]{t('tui.launch.col_subagent', self._lang)}:[/dim] {sub}  "
                f"[dim]{t('tui.launch.col_binary', self._lang)}:[/dim] {bin_mark}"
            )
            item = ListItem(Static(label))
            item._pick_kind = "cli"  # type: ignore[attr-defined]
            item._cli_id = row.cli_id  # type: ignore[attr-defined]
            lv.mount(item)

        if self._selected_cli_id:
            self._restore_selection(lv, self._selected_cli_id)
        elif lv.children:
            lv.index = 0
            first = lv.children[0]
            self._selected_cli_id = getattr(first, "_cli_id", None)
        self._update_detail(self._selected_cli_id)
        self._sync_action_buttons(assigning=False)

    def _restore_selection(self, lv: ListView, cli_id: str) -> None:
        for i, child in enumerate(lv.children):
            if getattr(child, "_cli_id", None) == cli_id:
                lv.index = i
                return

    def _row_for(self, cli_id: str | None):
        if not cli_id:
            return None
        for row in self._rows():
            if row.cli_id == cli_id:
                return row
        return None

    def _update_detail(self, cli_id: str | None) -> None:
        detail = self.query_one("#launch-detail", Static)
        row = self._row_for(cli_id)
        if row is None:
            detail.update(t("tui.launch.select_cli", self._lang))
            return
        assigned = (
            row.agent_slot
            if row.assigned
            else t("tui.launch.not_assigned", self._lang)
        )
        binary = row.binary or t("tui.launch.binary_missing", self._lang)
        detail.update(
            f"[bold]{row.display_name}[/bold] — {row.description}\n"
            f"{t('tui.launch.col_subagent', self._lang)}: [cyan]{assigned}[/cyan] · "
            f"{t('tui.launch.col_model', self._lang)}: {row.model_slot} · "
            f"{t('tui.launch.col_binary', self._lang)}: {binary}"
        )

    def _sync_action_buttons(self, *, assigning: bool) -> None:
        assign_btn = self.query_one("#btn-launch-assign", Button)
        unassign_btn = self.query_one("#btn-launch-unassign", Button)
        assign_btn.disabled = assigning
        row = self._row_for(self._selected_cli_id)
        unassign_btn.disabled = assigning or not (row and row.assigned)

    def _notify_host(self, message: str) -> None:
        if hasattr(self._host, "transcript_write"):
            self._host.transcript_write(f"[dim]{message}[/dim]")
        self.app.notify(message[:160])

    @on(ListView.Selected)
    def _on_list_selected(self, event: ListView.Selected) -> None:
        item = event.item
        kind = getattr(item, "_pick_kind", None)
        if kind == "cli":
            self._selected_cli_id = getattr(item, "_cli_id", None)
            self._update_detail(self._selected_cli_id)
            self._sync_action_buttons(assigning=False)
            return
        if kind == "subagent" and self._assign_cli_id:
            agent_type = getattr(item, "_agent_type", "")
            try:
                assign_cli_to_subagent(self._profile, self._assign_cli_id, agent_type)
            except ValueError as exc:
                self.app.notify(str(exc)[:160])
                return
            cli_id = self._assign_cli_id
            self._notify_host(
                t(
                    "tui.launch.assigned",
                    self._lang,
                    cli=cli_id,
                    agent=agent_type,
                )
            )
            self._view = "clis"
            self._assign_cli_id = None
            self._selected_cli_id = cli_id
            self._render_list()

    def action_back_or_close(self) -> None:
        if self._view == "assign":
            self._view = "clis"
            self._assign_cli_id = None
            self._render_list()
            return
        self.dismiss(None)

    @on(Button.Pressed, "#btn-launch-assign")
    def _on_assign(self) -> None:
        if not self._selected_cli_id:
            self.app.notify(t("tui.launch.select_cli", self._lang))
            return
        self._view = "assign"
        self._assign_cli_id = self._selected_cli_id
        self._render_list()

    @on(Button.Pressed, "#btn-launch-unassign")
    def _on_unassign(self) -> None:
        if not self._selected_cli_id:
            return
        row = self._row_for(self._selected_cli_id)
        if not row or not row.assigned:
            return
        agent = row.agent_slot
        unassign_cli_subagent(self._profile, self._selected_cli_id)
        self._notify_host(
            t(
                "tui.launch.unassigned",
                self._lang,
                cli=self._selected_cli_id,
                agent=agent,
            )
        )
        self._render_list()

    @on(Button.Pressed, "#btn-launch-refresh")
    def _on_refresh(self) -> None:
        self._render_list()

    @on(Button.Pressed, "#btn-launch-close")
    def _on_close(self) -> None:
        self.dismiss(None)


def open_launch_manager(host: Any) -> None:
    if not launch_supported():
        lang = host_locale(host)
        msg = t("tui.launch.unsupported", lang)
        if hasattr(host, "transcript_write"):
            host.transcript_write(f"[yellow]{msg}[/yellow]")
        raise RuntimeError(msg)
    if not hasattr(host, "push_screen"):
        raise RuntimeError("Launch manager requires TUI (push_screen)")
    host.push_screen(LaunchManagerScreen(host))