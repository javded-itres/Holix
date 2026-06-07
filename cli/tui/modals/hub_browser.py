"""In-TUI skill hub browser (parity with CLI interactive browse + agent assign)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    ListItem,
    ListView,
    ProgressBar,
    Select,
    SelectionList,
    Static,
)

from core.hub.catalog import SOURCES, CatalogRow, fetch_catalog_rows, parse_selection
from core.hub.claude_marketplace import MARKETPLACES
from core.hub.importer import SkillImporter
from core.hub.installed import InstalledItem, installed_flat_rows, remove_hub_install
from core.hub.slash_registry import rebuild_slash_registry

HUB_VIEW_MODES: list[tuple[str, str]] = [
    ("Search catalog", "search"),
    ("Installed (skills · plugins · MCP)", "installed"),
]


def _agent_slot_options(config: Any) -> list[tuple[str, str, bool]]:
    from core.skills.assignments import known_agent_slots

    slots = known_agent_slots(
        getattr(config, "skill_assignments", None),
        getattr(config, "agent_models", None),
    )
    return [(slot, slot, slot == "main") for slot in slots]


def _catalog_select_options() -> list[tuple[str, str]]:
    """Textual Select: (display label, value id)."""
    return [(label, sid) for _, sid, label in SOURCES]


class HubPickScreen(ModalScreen[str | None]):
    """Choose which skill catalog (hub) to open in the browser."""

    DEFAULT_CSS = """
    HubPickScreen {
        align: center middle;
    }
    #hub-pick-panel {
        width: 78%;
        max-width: 92;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 0 1 1 1;
    }
    #hub-pick-list {
        height: auto;
        min-height: 10;
        max-height: 18;
        border: solid $primary-darken-2;
        margin: 1 0;
    }
    #hub-pick-hint {
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm_pick", "Open"),
        Binding("1", "pick_1", "Claude official", show=False),
        Binding("2", "pick_2", "Claude Code", show=False),
        Binding("3", "pick_3", "ClawHub", show=False),
        Binding("4", "pick_4", "skills.sh", show=False),
        Binding("5", "pick_5", "Hermes", show=False),
    ]

    def __init__(self, profile: str, config: Any, *, initial_index: int = 2) -> None:
        super().__init__()
        self._profile = profile
        self._config = config
        self._initial_index = max(0, min(initial_index, len(SOURCES) - 1))

    def compose(self) -> ComposeResult:
        with Vertical(id="hub-pick-panel"):
            yield Header(show_clock=False)
            yield Static("[bold]Choose Skill Hub catalog[/bold]", id="hub-pick-title")
            yield Static(
                "[dim]↑↓ select · Enter open · 1–5 quick pick · Esc cancel[/dim]",
                id="hub-pick-hint",
            )
            yield ListView(
                *[
                    ListItem(
                        Static(
                            f"[bold]{key}[/bold]  {label}\n[dim]{sid}[/dim]",
                            expand=True,
                        )
                    )
                    for key, sid, label in SOURCES
                ],
                id="hub-pick-list",
            )
            yield Footer()

    def on_mount(self) -> None:
        self.title = "Hub"
        lv = self.query_one("#hub-pick-list", ListView)
        if lv.children:
            lv.index = self._initial_index
            lv.focus()

    def _source_at_index(self, index: int | None) -> str | None:
        if index is None or index < 0 or index >= len(SOURCES):
            return None
        return SOURCES[index][1]

    def _open_catalog(self, source_id: str) -> None:
        self.dismiss(source_id)

    def action_confirm_pick(self) -> None:
        lv = self.query_one("#hub-pick-list", ListView)
        source = self._source_at_index(lv.index)
        if source:
            self._open_catalog(source)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick_1(self) -> None:
        self._open_catalog(SOURCES[0][1])

    def action_pick_2(self) -> None:
        self._open_catalog(SOURCES[1][1])

    def action_pick_3(self) -> None:
        self._open_catalog(SOURCES[2][1])

    def action_pick_4(self) -> None:
        self._open_catalog(SOURCES[3][1])

    def action_pick_5(self) -> None:
        self._open_catalog(SOURCES[4][1])

    @on(ListView.Selected, "#hub-pick-list")
    def _on_pick_selected(self, event: ListView.Selected) -> None:
        try:
            lv = self.query_one("#hub-pick-list", ListView)
            idx = lv.children.index(event.item)
        except Exception:
            idx = lv.index if (lv := self.query_one("#hub-pick-list", ListView)).index is not None else None
        source = self._source_at_index(idx)
        if source:
            self._open_catalog(source)


class HubRemoveConfirmScreen(ModalScreen[bool]):
    """Confirm removal of a hub-installed skill/plugin bundle."""

    DEFAULT_CSS = """
    HubRemoveConfirmScreen {
        align: center middle;
    }
    #hub-remove-dialog {
        width: 72%;
        max-width: 90;
        height: auto;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }
    #hub-remove-buttons {
        align: center middle;
        height: auto;
        padding-top: 1;
    }
    #hub-remove-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Remove"),
    ]

    def __init__(self, title: str, entry_id: str) -> None:
        super().__init__()
        self._title = title
        self._entry_id = entry_id

    def compose(self) -> ComposeResult:
        with Container(id="hub-remove-dialog"):
            yield Static(
                f"[bold]Remove hub install?[/bold]\n\n"
                f"[cyan]{self._title}[/cyan]\n"
                f"[dim]id: {self._entry_id}[/dim]\n\n"
                "Deletes bundle under skills/_hub and lockfile entry.",
                id="hub-remove-body",
            )
            with Horizontal(id="hub-remove-buttons"):
                yield Button("Remove", id="hub-remove-ok", variant="error")
                yield Button("Cancel", id="hub-remove-cancel", variant="default")

    @on(Button.Pressed, "#hub-remove-ok")
    def action_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#hub-remove-cancel")
    def action_cancel(self) -> None:
        self.dismiss(False)


class HubAssignAgentsScreen(ModalScreen[list[str] | None]):
    """Assign freshly installed skills to agent slots."""

    DEFAULT_CSS = """
    HubAssignAgentsScreen {
        align: center middle;
    }
    #hub-assign-panel {
        width: 70%;
        max-width: 90;
        height: auto;
        max-height: 70%;
        border: solid $success;
        background: $surface;
        padding: 1 2;
    }
    #hub-assign-slots {
        height: auto;
        max-height: 16;
        margin: 1 0;
    }
    #hub-assign-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }
    #hub-assign-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [("escape", "skip", "Skip")]

    def __init__(self, profile: str, config: Any, skill_names: list[str]) -> None:
        super().__init__()
        self._profile = profile
        self._config = config
        self._skill_names = list(dict.fromkeys(skill_names))

    def compose(self) -> ComposeResult:
        names = ", ".join(self._skill_names)
        options = _agent_slot_options(self._config)
        with Vertical(id="hub-assign-panel"):
            yield Static(f"Assign skills to agents\n[dim]{names}[/dim]", id="hub-assign-title")
            yield SelectionList(*options, id="hub-assign-slots", compact=True)
            with Horizontal(id="hub-assign-buttons"):
                yield Button("Assign", id="hub-assign-ok", variant="success")
                yield Button("Skip", id="hub-assign-skip", variant="default")
            yield Static(
                "[dim]Or type agents below (comma-separated)[/dim]",
                id="hub-assign-hint",
            )
            yield Input(placeholder="main, coder, researcher", id="hub-assign-input", value="main")

    @on(Button.Pressed, "#hub-assign-ok")
    def _on_assign(self) -> None:
        slots = self._selected_slots()
        if not slots:
            self.notify("Select at least one agent or enter names", severity="warning")
            return
        used = self._persist(slots)
        if used:
            self.dismiss(used)
        else:
            self.notify("No valid agent slots", severity="warning")

    @on(Button.Pressed, "#hub-assign-skip")
    def action_skip(self) -> None:
        self.dismiss(None)

    def _selected_slots(self) -> list[str]:
        from core.skills.assignments import known_agent_slots

        valid = set(
            known_agent_slots(
                getattr(self._config, "skill_assignments", None),
                getattr(self._config, "agent_models", None),
            )
        )
        picked: list[str] = []
        try:
            sl = self.query_one("#hub-assign-slots", SelectionList)
            for sel in sl.selected:
                name = str(sel)
                if name in valid:
                    picked.append(name)
        except Exception:
            pass
        if picked:
            return picked
        raw = ""
        try:
            raw = self.query_one("#hub-assign-input", Input).value or ""
        except Exception:
            pass
        return [a.strip() for a in raw.split(",") if a.strip() and a.strip() in valid]

    def _persist(self, slots: list[str]) -> list[str]:
        from cli.core import get_profile_manager
        from core.skills.assignments import apply_skills_to_agent_slots

        manager = get_profile_manager()
        return apply_skills_to_agent_slots(
            self._config,
            self._profile,
            manager,
            self._skill_names,
            ",".join(slots),
        )


class HubBrowserScreen(ModalScreen[bool]):
    """Modal hub browser: catalog, search, install, assign agents."""

    DEFAULT_CSS = """
    HubBrowserScreen {
        align: center middle;
    }
    #hub-panel {
        width: 92%;
        height: 88%;
        border: solid $primary;
        background: $surface;
        padding: 0 1;
    }
    #hub-toolbar {
        height: auto;
        padding: 0 0 1 0;
    }
    #hub-mode {
        width: 36;
        min-width: 24;
    }
    #hub-browse-tools {
        height: auto;
        width: 1fr;
    }
    #hub-browse-tools.hidden {
        display: none;
    }
    #hub-catalog {
        width: 42;
        min-width: 28;
    }
    #hub-query {
        width: 1fr;
        min-width: 16;
    }
    #hub-search-btn {
        width: auto;
        min-width: 10;
    }
    #hub-status {
        height: auto;
        min-height: 2;
        padding: 0 1;
        color: $text-muted;
    }
    #hub-progress-row {
        height: auto;
        padding: 0 1 1 1;
    }
    #hub-progress-row.hidden {
        display: none;
    }
    #hub-progress-label {
        height: auto;
        min-height: 1;
        color: $text-muted;
    }
    #hub-progress {
        width: 100%;
        margin-top: 1;
    }
    #hub-results {
        height: 1fr;
        min-height: 14;
        border: solid $primary-darken-2;
    }
    #hub-results ListItem {
        padding: 0 1;
    }
    #hub-actions {
        height: auto;
        padding: 1 0;
    }
    #hub-mcp-row {
        height: auto;
        padding: 0 0 1 0;
    }
    #hub-mcp-row.hidden {
        display: none;
    }
    .hub-row-actions Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("ctrl+s", "search", "Search"),
        Binding("ctrl+i", "install_picked", "Install"),
        Binding("ctrl+l", "show_installed", "Installed list"),
        Binding("delete,backspace", "remove_hub", "Remove hub item"),
    ]

    def __init__(
        self,
        profile: str,
        config: Any,
        *,
        apply_mcp_fn: Any = None,
        default_source: str = "clawhub",
        initial_mode: str = "search",
    ) -> None:
        super().__init__()
        self._profile = profile
        self._config = config
        self._apply_mcp_fn = apply_mcp_fn
        self._rows: list[CatalogRow] = []
        self._installed_items: list[InstalledItem] = []
        self._installed_lv_rows: list[InstalledItem | None] = []
        self._source_id = default_source
        self._default_source = default_source
        self._mode = "installed" if initial_mode == "installed" else "search"
        self._searching = False
        self._installing = False

    def compose(self) -> ComposeResult:
        with Vertical(id="hub-panel"):
            yield Header(show_clock=False)
            yield Static(
                "Skill Hub — pick catalog, Search, install  [dim](Ctrl+S · Ctrl+I)[/dim]",
                id="hub-title",
            )
            with Horizontal(id="hub-toolbar"):
                yield Select(
                    HUB_VIEW_MODES,
                    id="hub-mode",
                    value=self._mode,
                    allow_blank=False,
                    compact=True,
                )
                with Horizontal(id="hub-browse-tools"):
                    yield Select(
                        _catalog_select_options(),
                        id="hub-catalog",
                        value=self._default_source,
                        allow_blank=False,
                        compact=True,
                    )
                    yield Input(placeholder="Search (empty = top list)", id="hub-query")
                    yield Button("Search", id="hub-search", variant="primary")
            with Horizontal(id="hub-mcp-row", classes="hidden"):
                yield Checkbox("Install bundled MCP into profile", id="hub-with-mcp", value=True)
            yield ListView(id="hub-results")
            yield Static("Loading catalog…", id="hub-status")
            with Vertical(id="hub-progress-row", classes="hidden"):
                yield Static("", id="hub-progress-label")
                yield ProgressBar(
                    total=100,
                    id="hub-progress",
                    show_eta=False,
                )
            with Vertical(id="hub-actions"):
                yield Input(placeholder="1,2,3", id="hub-pick")
                with Horizontal(classes="hub-row-actions"):
                    yield Button("Install selected", id="hub-install", variant="success")
                    yield Button("Install highlighted", id="hub-install-one", variant="primary")
                    yield Button("Refresh installed", id="hub-refresh-installed", variant="default")
                    yield Button("Remove hub", id="hub-remove", variant="error")
                yield Static(
                    "[dim]Catalogs: Claude · ClawHub · skills.sh · Hermes[/dim]",
                    id="hub-footnote",
                )
            yield Footer()

    def on_mount(self) -> None:
        self.title = "Hub"
        self._sync_mode_ui()
        if self._mode == "installed":
            self._show_installed()
        else:
            self._sync_mcp_row()
            self.call_after_refresh(self._start_search)

    def _search_query(self) -> str:
        try:
            return self.query_one("#hub-query", Input).value or ""
        except Exception:
            return ""

    def _current_mode(self) -> str:
        try:
            val = self.query_one("#hub-mode", Select).value
            if isinstance(val, tuple):
                return str(val[1])
            return str(val) if val not in (None, Select.BLANK) else self._mode
        except Exception:
            return self._mode

    def _sync_mode_ui(self) -> None:
        mode = self._current_mode()
        self._mode = mode
        try:
            browse = self.query_one("#hub-browse-tools")
            actions = self.query_one("#hub-actions")
            pick = self.query_one("#hub-pick", Input)
            if mode == "installed":
                browse.add_class("hidden")
                pick.display = False
                self.query_one("#hub-install", Button).display = False
                self.query_one("#hub-install-one", Button).display = False
                self.query_one("#hub-refresh-installed", Button).display = True
                self.query_one("#hub-remove", Button).display = True
                self.query_one("#hub-footnote", Static).update(
                    "[dim]↑↓ hub row · Remove / Delete · MCP: /mcp remove <name>[/dim]"
                )
            else:
                browse.remove_class("hidden")
                pick.display = True
                self.query_one("#hub-install", Button).display = True
                self.query_one("#hub-install-one", Button).display = True
                self.query_one("#hub-refresh-installed", Button).display = False
                self.query_one("#hub-remove", Button).display = False
                self.query_one("#hub-footnote", Static).update(
                    "[dim]Catalogs: Claude · ClawHub · skills.sh · Hermes[/dim]"
                )
            _ = actions
        except Exception:
            pass

    @on(Select.Changed, "#hub-mode")
    def _on_mode_changed(self) -> None:
        self._sync_mode_ui()
        if self._mode == "installed":
            self._show_installed()
        else:
            self._sync_mcp_row()
            self._start_search()

    def action_show_installed(self) -> None:
        try:
            self.query_one("#hub-mode", Select).value = "installed"
        except Exception:
            pass
        self._mode = "installed"
        self._sync_mode_ui()
        self._show_installed()

    @on(Button.Pressed, "#hub-refresh-installed")
    def _on_refresh_installed(self) -> None:
        self._show_installed()

    def _highlighted_installed_item(self) -> InstalledItem | None:
        try:
            lv = self.query_one("#hub-results", ListView)
            if lv.index is None or lv.index < 0 or lv.index >= len(self._installed_lv_rows):
                return None
            return self._installed_lv_rows[lv.index]
        except Exception:
            return None

    @on(Button.Pressed, "#hub-remove")
    def _on_remove_pressed(self) -> None:
        self.action_remove_hub()

    def action_remove_hub(self) -> None:
        if self._mode != "installed":
            self.notify("Switch to Installed view first", severity="warning")
            return
        item = self._highlighted_installed_item()
        if not item:
            self.notify("Highlight an item in the list", severity="warning")
            return
        if item.kind != "hub" or not item.hub_entry_id:
            self.notify(
                "Only hub installs can be removed here (MCP: /mcp remove, local: delete .md)",
                severity="warning",
            )
            return
        self._run_remove_hub(item)

    @work(exclusive=True)
    async def _run_remove_hub(self, item: InstalledItem) -> None:
        entry_id = item.hub_entry_id or ""
        confirmed = await self.app.push_screen_wait(
            HubRemoveConfirmScreen(item.title, entry_id)
        )
        if not confirmed:
            return
        self._set_status(f"[dim]Removing {item.title}…[/dim]")
        try:
            names = await asyncio.to_thread(
                remove_hub_install,
                self._profile,
                self._config,
                entry_id,
            )
            self.notify(f"Removed: {', '.join(names)}", severity="information")
            self._set_status(f"[green]Removed[/green] {entry_id} ({', '.join(names)})")
        except KeyError:
            self.notify(f"Unknown entry: {entry_id}", severity="error")
            self._set_status(f"[red]Not found: {entry_id}[/red]")
        except Exception as e:
            self.notify(str(e), severity="error")
            self._set_status(f"[red]Remove failed: {e}[/red]")
        self._show_installed()

    def _show_installed(self) -> None:
        self._rows = []
        lv = self.query_one("#hub-results", ListView)
        lv.clear()
        flat = installed_flat_rows(self._config)
        self._installed_items = [item for kind, item in flat if kind == "item" and item.kind != "empty"]
        self._installed_lv_rows = []

        for row_kind, item in flat:
            if item.kind == "header":
                self._installed_lv_rows.append(None)
                lv.append(ListItem(Static(f"[bold]{item.title}[/bold]", expand=True)))
            elif item.kind == "empty":
                self._installed_lv_rows.append(None)
                lv.append(ListItem(Static(f"  [dim]{item.title}[/dim]", expand=True)))
            elif item.kind == "hub":
                self._installed_lv_rows.append(item)
                eid = f" · [dim]{item.hub_entry_id}[/dim]" if item.hub_entry_id else ""
                lv.append(
                    ListItem(
                        Static(
                            f"  [cyan]{item.title}[/cyan] [dim](hub)[/dim]\n  {item.subtitle}{eid}",
                            expand=True,
                        )
                    )
                )
            elif item.kind == "mcp":
                self._installed_lv_rows.append(item)
                lv.append(
                    ListItem(
                        Static(
                            f"  [green]{item.title}[/green] [dim](MCP)[/dim]\n  {item.subtitle}",
                            expand=True,
                        )
                    )
                )
            else:
                self._installed_lv_rows.append(item)
                lv.append(
                    ListItem(
                        Static(
                            f"  {item.title} [dim](skill)[/dim]\n  {item.subtitle}",
                            expand=True,
                        )
                    )
                )

        hub_n = sum(1 for i in self._installed_items if i.kind == "hub")
        mcp_n = sum(1 for i in self._installed_items if i.kind == "mcp")
        skill_n = sum(1 for i in self._installed_items if i.kind == "skill")
        self._set_status(
            f"Installed: {hub_n} hub · {mcp_n} MCP · {skill_n} local skills  "
            "[dim](Delete = remove hub · Ctrl+L refresh)[/dim]"
        )

    def _start_search(self) -> None:
        if self._mode == "installed" or self._searching:
            return
        self._source_id = self._current_source()
        self._run_search(self._source_id, self._search_query())

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#hub-status", Static).update(text)
        except Exception:
            pass

    def _set_install_buttons_enabled(self, enabled: bool) -> None:
        for sel in ("#hub-install", "#hub-install-one"):
            try:
                self.query_one(sel, Button).disabled = not enabled
            except Exception:
                pass

    def _show_install_progress(self, step: int, total: int, label: str) -> None:
        try:
            self.query_one("#hub-progress-row").remove_class("hidden")
            self.query_one("#hub-progress-label", Static).update(
                f"[dim]Installing {step}/{total}:[/dim] [bold]{label}[/bold]"
            )
            bar = self.query_one("#hub-progress", ProgressBar)
            bar.update(total=max(total, 1), progress=max(0, step - 1))
        except Exception:
            pass

    def _advance_install_progress(self, step: int, total: int, label: str) -> None:
        try:
            self.query_one("#hub-progress-label", Static).update(
                f"[dim]Installing {step}/{total}:[/dim] [bold]{label}[/bold]"
            )
            self.query_one("#hub-progress", ProgressBar).update(
                total=max(total, 1),
                progress=step,
            )
        except Exception:
            pass

    def _hide_install_progress(self) -> None:
        try:
            self.query_one("#hub-progress-row").add_class("hidden")
            self.query_one("#hub-progress", ProgressBar).update(progress=0)
        except Exception:
            pass

    def _sync_mcp_row(self) -> None:
        source = self._current_source()
        try:
            row = self.query_one("#hub-mcp-row")
            if source in MARKETPLACES:
                row.remove_class("hidden")
            else:
                row.add_class("hidden")
        except Exception:
            pass

    def _current_source(self) -> str:
        try:
            sel = self.query_one("#hub-catalog", Select)
            val = sel.value
            if isinstance(val, Select.BLANK):
                return self._source_id
            if isinstance(val, tuple):
                return str(val[1] if len(val) > 1 else val[0])
            text = str(val).strip()
            if text in MARKETPLACES or text in {sid for _, sid, _ in SOURCES}:
                return text
            for _, sid, label in SOURCES:
                if text == label:
                    return sid
            return self._source_id
        except Exception:
            return self._source_id

    def _with_mcp(self) -> bool:
        if self._current_source() not in MARKETPLACES:
            return False
        try:
            return bool(self.query_one("#hub-with-mcp", Checkbox).value)
        except Exception:
            return True

    @on(Select.Changed, "#hub-catalog")
    def _on_catalog_changed(self) -> None:
        self._source_id = self._current_source()
        self._sync_mcp_row()
        self._start_search()

    def action_search(self) -> None:
        if self._mode == "installed":
            try:
                self.query_one("#hub-mode", Select).value = "search"
            except Exception:
                pass
            self._mode = "search"
            self._sync_mode_ui()
        self._start_search()

    def action_install_picked(self) -> None:
        self._on_install_pressed()

    @on(Button.Pressed, "#hub-search")
    def _on_search_pressed(self) -> None:
        self._start_search()

    @work(exclusive=True, group="hub_search")
    async def _run_search(self, source: str, query: str) -> None:
        self._searching = True
        self._set_status("[dim]Searching… (marketplace first load may take ~1 min)[/dim]")
        try:
            if source == "skills-sh" and not query.strip():
                self._show_error("skills.sh requires a search query (e.g. react, kubernetes)")
                return

            rows = await asyncio.to_thread(fetch_catalog_rows, source, query, limit=25)
            self._show_results(rows, source)
        except Exception as e:
            self._show_error(str(e))
        finally:
            self._searching = False

    def _show_error(self, msg: str) -> None:
        self._rows = []
        self._set_status(f"[red]{msg}[/red]")
        try:
            self.query_one("#hub-results", ListView).clear()
        except Exception:
            pass

    def _show_results(self, rows: list[CatalogRow], source: str) -> None:
        self._rows = rows
        lv = self.query_one("#hub-results", ListView)
        lv.clear()
        if not rows:
            self._set_status(
                f"[yellow]No matches[/yellow] in {source} — try another query or catalog (dropdown above)"
            )
            return
        for i, row in enumerate(rows, 1):
            mcp = " [MCP]" if row.has_mcp else ""
            text = f"{i}. [bold]{row.title}[/bold] ({row.category}){mcp}\n[dim]{row.summary}[/dim]"
            lv.append(ListItem(Static(text, expand=True)))
        if lv.index is None and lv.children:
            lv.index = 0
        self._set_status(f"{len(rows)} in {source} — numbers or ↑↓ + Install highlighted")

    def _resolve_install_indices(self) -> list[int] | None:
        if not self._rows:
            return None
        pick = ""
        try:
            pick = self.query_one("#hub-pick", Input).value or ""
        except Exception:
            pass
        indices = parse_selection(pick, len(self._rows))
        return indices or None

    def _highlighted_index(self) -> int | None:
        try:
            lv = self.query_one("#hub-results", ListView)
            if lv.index is not None and 0 <= lv.index < len(self._rows):
                return lv.index + 1
        except Exception:
            pass
        return None

    @on(Button.Pressed, "#hub-install")
    def _on_install_pressed(self) -> None:
        indices = self._resolve_install_indices()
        if not indices:
            self._set_status("Enter item numbers (e.g. 1,3) or use Install highlighted")
            return
        self._run_install(indices, self._with_mcp())

    @on(Button.Pressed, "#hub-install-one")
    def _on_install_highlighted(self) -> None:
        idx = self._highlighted_index()
        if idx is None:
            self._set_status("Highlight a result row first (↑↓ in the list)")
            return
        self._run_install([idx], self._with_mcp())

    @work(exclusive=True, group="hub_install")
    async def _run_install(self, indices: list[int], with_mcp: bool) -> None:
        if self._installing:
            return
        self._installing = True
        self._set_install_buttons_enabled(False)
        total = len(indices)
        rows_snapshot = list(self._rows)
        skills_dir = Path(self._config.skills_dir)
        importer = SkillImporter(skills_dir)
        apply_mcp = self._apply_mcp_fn

        installed_names: list[str] = []
        errors: list[str] = []
        has_mcp_plugin = False

        first = rows_snapshot[indices[0] - 1] if indices else None
        self._set_status(f"[dim]Installing {total} item(s)…[/dim]")
        self._show_install_progress(1, total, first.title if first else "…")

        def _install_one(row: CatalogRow) -> tuple[list[str], bool, str | None]:
            result = importer.install(row.install_spec)
            names = list(result.skill_names or [result.skill_name])
            err: str | None = None
            saw_mcp = bool(result.mcp_servers)
            if result.mcp_servers:
                if with_mcp and apply_mcp:
                    apply_mcp(result.mcp_servers, result.slug)
                else:
                    err = f"{row.title}: MCP skipped"
            return names, saw_mcp, err

        try:
            for step, idx in enumerate(indices, start=1):
                row = rows_snapshot[idx - 1]
                self._show_install_progress(step, total, row.title)
                try:
                    names, saw_mcp, err = await asyncio.to_thread(_install_one, row)
                    installed_names.extend(names)
                    if saw_mcp:
                        has_mcp_plugin = True
                    if err:
                        errors.append(err)
                    self._advance_install_progress(step, total, row.title)
                except Exception as e:
                    errors.append(f"{row.title}: {e}")
                    self._advance_install_progress(step, total, row.title)

            await asyncio.to_thread(rebuild_slash_registry, skills_dir)
        except Exception as e:
            errors.append(str(e))
        finally:
            self._installing = False
            self._hide_install_progress()
            self._set_install_buttons_enabled(True)

        unique = list(dict.fromkeys(installed_names))
        self._install_finished(unique, errors, has_mcp_plugin and not with_mcp)

    def _install_finished(
        self,
        installed_names: list[str],
        errors: list[str],
        mcp_skipped: bool,
    ) -> None:
        parts: list[str] = []
        if installed_names:
            parts.append(f"Installed: {', '.join(installed_names)}")
        if errors:
            parts.append(f"Issues: {'; '.join(errors[:3])}")
        if mcp_skipped:
            parts.append("MCP not merged (checkbox off)")
        self._set_status(" · ".join(parts) or "Done")

        if installed_names:
            self._prompt_assign(installed_names)
        if self._mode == "installed":
            self._show_installed()

    @work(exclusive=True)
    async def _prompt_assign(self, skill_names: list[str]) -> None:
        used = await self.app.push_screen_wait(
            HubAssignAgentsScreen(self._profile, self._config, skill_names)
        )
        if used:
            self._set_status(
                f"Assigned {', '.join(skill_names)} → {', '.join(used)} · Ctrl+S to search again"
            )
        else:
            self._set_status("Install done — assign skipped · Ctrl+S to search again")

    def action_dismiss(self) -> None:
        self.dismiss(True)


def _hub_apply_mcp_factory(profile: str, config: Any):
    def _apply_mcp(servers: dict, slug: str) -> int:
        if not servers:
            return 0
        from cli.core import get_profile_manager
        from core.hub.claude_mcp import merge_into_profile_servers

        manager = get_profile_manager()
        merged = merge_into_profile_servers(
            dict(getattr(config, "mcp_servers", {}) or {}),
            slug,
            servers,
        )
        config.mcp_servers = merged
        manager.save_profile(profile, config)
        return len(servers)

    return _apply_mcp


def _initial_pick_index(source_id: str | None) -> int:
    if not source_id:
        return 2
    for i, (_, sid, _) in enumerate(SOURCES):
        if sid == source_id:
            return i
    return 2


def open_hub_pick(
    app: Any,
    profile: str,
    config: Any,
    *,
    highlight_source: str | None = None,
) -> None:
    """Show catalog picker, then open the hub browser for the chosen source."""

    if not hasattr(app, "push_screen"):
        return

    apply_mcp = _hub_apply_mcp_factory(profile, config)

    def _after_pick(source_id: str | None) -> None:
        if source_id:
            app.push_screen(
                HubBrowserScreen(
                    profile,
                    config,
                    apply_mcp_fn=apply_mcp,
                    default_source=source_id,
                )
            )

    app.push_screen(
        HubPickScreen(profile, config, initial_index=_initial_pick_index(highlight_source)),
        _after_pick,
    )


def open_hub_browser(
    app: Any,
    profile: str,
    config: Any,
    *,
    default_source: str = "clawhub",
    initial_mode: str = "search",
) -> None:
    """Push hub browser modal if the host is a Textual App."""

    if hasattr(app, "push_screen"):
        app.push_screen(
            HubBrowserScreen(
                profile,
                config,
                apply_mcp_fn=_hub_apply_mcp_factory(profile, config),
                default_source=default_source,
                initial_mode=initial_mode,
            )
        )