"""TUI modal: create and edit custom sub-agent types."""

from __future__ import annotations

from typing import Any, Literal

from core.external_cli.registry import list_cli_specs
from core.i18n import host_locale, t
from core.subagents.registry import is_builtin_subagent, list_available_subagents
from core.subagents.store import (
    DEFAULT_CUSTOM_TOOLS,
    SUBAGENT_TOOL_CHOICES,
    CustomSubAgentType,
    SubAgentTypeStore,
    cleanup_custom_type_profile_bindings,
    sync_custom_type_profile_bindings,
    validate_custom_type_name,
)
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    ListItem,
    ListView,
    Select,
    SelectionList,
    Static,
    TextArea,
)

_INHERIT_MODEL = "__inherit__"
_NO_CLI = "__none__"


def _load_profile_config(profile: str) -> Any:
    from cli.core import get_profile_manager

    return get_profile_manager().load_profile(profile)


def _skill_options(profile: str, config: Any) -> list[tuple[str, str, bool]]:
    from pathlib import Path

    from core.hub.normalize import discover_skill_files, parse_skill_file

    names: set[str] = set()
    skills_dir = Path(getattr(config, "skills_dir", "") or "")
    if skills_dir.is_dir():
        for path in discover_skill_files(skills_dir):
            skill = parse_skill_file(path)
            if skill and skill.get("name"):
                names.add(str(skill["name"]))
    return [(n, n, False) for n in sorted(names)]


def _mcp_options(config: Any) -> list[tuple[str, str, bool]]:
    servers = getattr(config, "mcp_servers", None) or {}
    return [(name, name, False) for name in sorted(servers.keys())]


def _model_select_options(profile: str) -> list[tuple[str, str]]:
    from integrations.telegram.model_switch import build_models_menu

    options: list[tuple[str, str]] = [("inherit parent model", _INHERIT_MODEL)]
    menu = build_models_menu(profile)
    for preset in menu.presets:
        label = f"{preset.label} ({preset.provider}/{preset.model})"
        options.append((label, preset.slot_id))
    return options


def _cli_select_options() -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = [("none", _NO_CLI)]
    for spec in list_cli_specs():
        options.append((spec.display_name, spec.cli_id))
    return options


def _tool_options(selected: set[str]) -> list[tuple[str, str, bool]]:
    return [(tool, tool, tool in selected) for tool in SUBAGENT_TOOL_CHOICES]


def _decode_model_slot(value: str) -> str:
    return "" if value == _INHERIT_MODEL else value


def _decode_cli_id(value: str) -> str:
    return "" if value == _NO_CLI else value


def _encode_model_slot(value: str) -> str:
    return _INHERIT_MODEL if not value else value


def _encode_cli_id(value: str) -> str:
    return _NO_CLI if not value else value


class SubagentTypesManagerScreen(ModalScreen[None]):
    """Manage custom sub-agent types for the active profile."""

    DEFAULT_CSS = """
    SubagentTypesManagerScreen {
        align: center middle;
    }
    #sat-panel {
        width: 94%;
        max-width: 120;
        height: 86%;
        border: solid $primary;
        background: $surface;
        padding: 0 1 1 1;
    }
    #sat-type-list {
        height: 1fr;
        min-height: 10;
        max-height: 1fr;
        border: solid $primary-darken-2;
        margin: 1 0;
    }
    #sat-form {
        display: none;
        height: 1fr;
        min-height: 10;
        border: solid $primary-darken-2;
        margin: 1 0;
    }
    #sat-form TextArea {
        height: 8;
        margin-bottom: 1;
    }
    #sat-form SelectionList {
        height: 5;
        margin-bottom: 1;
    }
    #sat-detail {
        height: auto;
        max-height: 4;
        padding: 0 1;
        color: $text-muted;
    }
    #sat-actions {
        height: auto;
        min-height: 3;
        padding-top: 1;
        align: center middle;
    }
    #sat-actions Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "back_or_close", "Back"),
        Binding("q", "back_or_close", "Back", show=False),
        Binding("c", "create_type", "Create", show=False),
        Binding("e", "edit_type", "Edit", show=False),
        Binding("d", "delete_type", "Delete", show=False),
        Binding("r", "refresh_types", "Refresh", show=False),
    ]

    def __init__(self, host: Any) -> None:
        super().__init__()
        self._host = host
        self._profile = str(getattr(host, "profile", None) or "default")
        self._lang = host_locale(host)
        self._config = _load_profile_config(self._profile)
        self._store = SubAgentTypeStore(self._profile)
        self._view: Literal["list", "form"] = "list"
        self._editing_name: str | None = None
        self._selected_name: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="sat-panel"):
            yield Header(show_clock=False)
            yield Static("", id="sat-title")
            yield Static("", id="sat-hint")
            yield ListView(id="sat-type-list")
            with ScrollableContainer(id="sat-form"):
                yield Input(placeholder="security-auditor", id="sat-name")
                yield Input(placeholder="Short description", id="sat-desc")
                yield TextArea(id="sat-prompt")
                yield Static("", id="sat-label-tools")
                yield SelectionList(id="sat-tools")
                yield Static("", id="sat-label-skills")
                yield SelectionList(id="sat-skills")
                yield Static("", id="sat-label-mcp")
                yield SelectionList(id="sat-mcp")
                yield Static("", id="sat-label-model")
                yield Select(
                    (("inherit parent model", _INHERIT_MODEL),),
                    id="sat-model",
                    value=_INHERIT_MODEL,
                )
                yield Static("", id="sat-label-cli")
                yield Select((("none", _NO_CLI),), id="sat-cli", value=_NO_CLI)
            yield Static("", id="sat-detail")
            with Horizontal(id="sat-actions"):
                yield Button("Create", id="btn-sat-create", variant="success")
                yield Button("Edit", id="btn-sat-edit")
                yield Button("Delete", id="btn-sat-delete", variant="error")
                yield Button("Save", id="btn-sat-save", variant="success")
                yield Button("Cancel", id="btn-sat-cancel")
                yield Button("Refresh", id="btn-sat-refresh")
                yield Button("Close", id="btn-sat-close")
            yield Footer()

    def on_mount(self) -> None:
        self.title = t("tui.subagent_types.title", self._lang)
        self._apply_labels()
        self.query_one("#sat-form", ScrollableContainer).display = False
        self._show_view("list")

    def _apply_labels(self) -> None:
        self.query_one("#btn-sat-create", Button).label = t(
            "tui.subagent_types.create", self._lang
        )
        self.query_one("#btn-sat-edit", Button).label = t("tui.subagent_types.edit", self._lang)
        self.query_one("#btn-sat-delete", Button).label = t(
            "tui.subagent_types.delete", self._lang
        )
        self.query_one("#btn-sat-save", Button).label = t("tui.subagent_types.save", self._lang)
        self.query_one("#btn-sat-cancel", Button).label = t(
            "tui.subagent_types.cancel", self._lang
        )
        self.query_one("#btn-sat-refresh", Button).label = t(
            "tui.subagent_types.refresh", self._lang
        )
        self.query_one("#btn-sat-close", Button).label = t("tui.subagent_types.close", self._lang)
        self.query_one("#sat-label-tools", Static).update(
            t("tui.subagent_types.tools", self._lang)
        )
        self.query_one("#sat-label-skills", Static).update(
            t("tui.subagent_types.skills", self._lang)
        )
        self.query_one("#sat-label-mcp", Static).update(t("tui.subagent_types.mcp", self._lang))
        self.query_one("#sat-label-model", Static).update(
            t("tui.subagent_types.model", self._lang)
        )
        self.query_one("#sat-label-cli", Static).update(
            t("tui.subagent_types.external_cli", self._lang)
        )

    def _show_view(self, view: Literal["list", "form"]) -> None:
        self._view = view
        list_view = self.query_one("#sat-type-list", ListView)
        form_wrap = self.query_one("#sat-form", ScrollableContainer)
        if view == "list":
            list_view.display = True
            form_wrap.display = False
            self._render_type_list()
            list_view.focus()
        else:
            list_view.display = False
            form_wrap.display = True
            self._render_form()
            form_wrap.scroll_home(animate=False)
            self.query_one("#sat-name", Input).focus()
        self._sync_action_buttons()

    def _sync_action_buttons(self) -> None:
        listing = self._view == "list"
        custom_selected = bool(
            self._selected_name and not is_builtin_subagent(self._selected_name or "")
        )
        for bid, show in (
            ("#btn-sat-create", listing),
            ("#btn-sat-edit", listing),
            ("#btn-sat-delete", listing),
            ("#btn-sat-save", not listing),
            ("#btn-sat-cancel", not listing),
            ("#btn-sat-refresh", listing),
            ("#btn-sat-close", True),
        ):
            self.query_one(bid, Button).display = show

        self.query_one("#btn-sat-edit", Button).disabled = not custom_selected
        self.query_one("#btn-sat-delete", Button).disabled = not custom_selected

    def _apply_list_selection(self, item: ListItem | None) -> None:
        detail = self.query_one("#sat-detail", Static)
        if item is None or not getattr(item, "_type_name", None):
            self._selected_name = None
            detail.update(t("tui.subagent_types.select_type", self._lang))
            self._sync_action_buttons()
            return
        self._selected_name = getattr(item, "_type_name", None)
        builtin = bool(getattr(item, "_builtin", True))
        kind = (
            t("tui.subagent_types.builtin", self._lang)
            if builtin
            else t("tui.subagent_types.custom", self._lang)
        )
        detail.update(f"{self._selected_name} · {kind}")
        self._sync_action_buttons()

    def _render_type_list(self) -> None:
        title = self.query_one("#sat-title", Static)
        hint = self.query_one("#sat-hint", Static)
        lv = self.query_one("#sat-type-list", ListView)
        lv.clear()
        title.update(
            f"[bold]{t('tui.subagent_types.title', self._lang)}[/bold]  "
            f"[dim]{self._profile}[/dim]"
        )
        hint.update(f"[dim]{t('tui.subagent_types.list_hint', self._lang)}[/dim]")
        items = list_available_subagents(profile=self._profile)
        if not items:
            lv.mount(
                ListItem(Static(f"[dim]{t('tui.subagent_types.empty', self._lang)}[/dim]"))
            )
            self._apply_list_selection(None)
            return
        for item in items:
            badge = (
                t("tui.subagent_types.builtin", self._lang)
                if item.get("builtin")
                else t("tui.subagent_types.custom", self._lang)
            )
            label = (
                f"[cyan]{item['name']}[/cyan]  [dim]{badge}[/dim]\n"
                f"   {(item.get('description') or '—')[:80]}"
            )
            row = ListItem(Static(label))
            row._type_name = item["name"]  # type: ignore[attr-defined]
            row._builtin = bool(item.get("builtin"))  # type: ignore[attr-defined]
            lv.mount(row)

        if self._selected_name:
            for i, child in enumerate(lv.children):
                if getattr(child, "_type_name", None) == self._selected_name:
                    lv.index = i
                    self._apply_list_selection(child if isinstance(child, ListItem) else None)
                    return
        if lv.children:
            lv.index = 0
            first = lv.children[0]
            self._apply_list_selection(first if isinstance(first, ListItem) else None)
        else:
            self._apply_list_selection(None)

    def _set_select_value(self, widget_id: str, value: str, options: list[tuple[str, str]]) -> None:
        sel = self.query_one(widget_id, Select)
        valid = {opt[1] for opt in options}
        pick = value if value in valid else options[0][1]
        sel.set_options(options)
        sel.value = pick

    def _render_form(self, *, custom: CustomSubAgentType | None = None) -> None:
        title = self.query_one("#sat-title", Static)
        hint = self.query_one("#sat-hint", Static)
        detail = self.query_one("#sat-detail", Static)
        creating = self._editing_name is None
        title.update(
            f"[bold]{t('tui.subagent_types.form_title', self._lang)}[/bold]  "
            f"[dim]{'+' if creating else self._editing_name}[/dim]"
        )
        hint.update(f"[dim]{t('tui.subagent_types.form_hint', self._lang)}[/dim]")
        detail.update("")

        name_input = self.query_one("#sat-name", Input)
        name_input.value = "" if creating else (custom.name if custom else self._editing_name or "")
        name_input.disabled = not creating

        desc_input = self.query_one("#sat-desc", Input)
        desc_input.value = custom.description if custom else ""

        prompt = self.query_one("#sat-prompt", TextArea)
        prompt.text = custom.system_prompt if custom else ""

        selected_tools = set(custom.tools if custom else DEFAULT_CUSTOM_TOOLS)
        tools_sl = self.query_one("#sat-tools", SelectionList)
        tools_sl.clear_options()
        for opt in _tool_options(selected_tools):
            tools_sl.add_option(opt)

        selected_skills = set(custom.skills if custom else [])
        skills_sl = self.query_one("#sat-skills", SelectionList)
        skills_sl.clear_options()
        for opt in _skill_options(self._profile, self._config):
            key, label, _ = opt
            skills_sl.add_option((key, label, key in selected_skills))

        selected_mcp = set(custom.mcp_servers if custom else [])
        mcp_sl = self.query_one("#sat-mcp", SelectionList)
        mcp_sl.clear_options()
        for opt in _mcp_options(self._config):
            key, label, _ = opt
            mcp_sl.add_option((key, label, key in selected_mcp))

        model_opts = _model_select_options(self._profile)
        model_pick = _encode_model_slot(custom.model_slot if custom else "")
        self._set_select_value("#sat-model", model_pick, model_opts)

        cli_opts = _cli_select_options()
        cli_pick = _encode_cli_id(custom.external_cli_id if custom else "")
        self._set_select_value("#sat-cli", cli_pick, cli_opts)

    def _selection_from_list(self, widget_id: str) -> list[str]:
        try:
            sl = self.query_one(widget_id, SelectionList)
            return [str(sel) for sel in sl.selected]
        except Exception:
            return []

    def _notify(self, message: str, *, severity: str = "information") -> None:
        if hasattr(self._host, "transcript_write"):
            self._host.transcript_write(message)
        self.notify(message, severity=severity)

    @on(ListView.Highlighted, "#sat-type-list")
    def _on_type_highlighted(self, event: ListView.Highlighted) -> None:
        if self._view != "list":
            return
        item = event.item
        if isinstance(item, ListItem):
            self._apply_list_selection(item)

    @on(ListView.Selected, "#sat-type-list")
    def _on_type_selected(self, event: ListView.Selected) -> None:
        if self._view != "list":
            return
        item = event.item
        if isinstance(item, ListItem):
            self._apply_list_selection(item)

    @on(Button.Pressed, "#btn-sat-create")
    def _on_create(self) -> None:
        self._editing_name = None
        self._config = _load_profile_config(self._profile)
        self._show_view("form")

    @on(Button.Pressed, "#btn-sat-edit")
    def _on_edit(self) -> None:
        if not self._selected_name or is_builtin_subagent(self._selected_name):
            self.notify(t("tui.subagent_types.builtin_readonly", self._lang), severity="warning")
            return
        custom = self._store.get(self._selected_name)
        if custom is None:
            self.notify(t("tui.subagent_types.not_found", self._lang), severity="error")
            return
        self._editing_name = custom.name
        self._config = _load_profile_config(self._profile)
        self._show_view("form")
        self._render_form(custom=custom)

    @on(Button.Pressed, "#btn-sat-delete")
    def _on_delete(self) -> None:
        if not self._selected_name or is_builtin_subagent(self._selected_name):
            self.notify(t("tui.subagent_types.builtin_readonly", self._lang), severity="warning")
            return
        removed = self._store.remove(self._selected_name)
        if removed is None:
            self.notify(t("tui.subagent_types.not_found", self._lang), severity="error")
            return
        cleanup_custom_type_profile_bindings(self._profile, removed.name)
        self._notify(
            t("tui.subagent_types.deleted", self._lang, name=removed.name),
            severity="warning",
        )
        self._selected_name = None
        self._render_type_list()

    @on(Button.Pressed, "#btn-sat-save")
    def _on_save(self) -> None:
        try:
            name = self.query_one("#sat-name", Input).value.strip()
            if self._editing_name:
                name = self._editing_name
            else:
                name = validate_custom_type_name(name)
            custom = CustomSubAgentType(
                name=name,
                description=self.query_one("#sat-desc", Input).value.strip(),
                system_prompt=self.query_one("#sat-prompt", TextArea).text.strip(),
                tools=self._selection_from_list("#sat-tools") or list(DEFAULT_CUSTOM_TOOLS),
                skills=self._selection_from_list("#sat-skills"),
                mcp_servers=self._selection_from_list("#sat-mcp"),
                model_slot=_decode_model_slot(
                    str(self.query_one("#sat-model", Select).value or _INHERIT_MODEL)
                ),
                external_cli_id=_decode_cli_id(
                    str(self.query_one("#sat-cli", Select).value or _NO_CLI)
                ),
            )
            if not custom.system_prompt:
                raise ValueError(t("tui.subagent_types.prompt_required", self._lang))
            previous = (
                self._editing_name if self._editing_name and self._editing_name != name else None
            )
            self._store.upsert(custom)
            sync_custom_type_profile_bindings(
                self._profile,
                custom,
                previous_name=previous,
            )
            self._notify(
                t("tui.subagent_types.saved", self._lang, name=custom.name),
                severity="information",
            )
            self._editing_name = None
            self._selected_name = custom.name
            self._show_view("list")
        except Exception as exc:
            self.notify(str(exc), severity="error")

    @on(Button.Pressed, "#btn-sat-cancel")
    def _on_cancel(self) -> None:
        self._editing_name = None
        self._show_view("list")

    @on(Button.Pressed, "#btn-sat-refresh")
    def _on_refresh(self) -> None:
        self._config = _load_profile_config(self._profile)
        self._render_type_list()

    @on(Button.Pressed, "#btn-sat-close")
    def _on_close(self) -> None:
        self.dismiss(None)

    def action_create_type(self) -> None:
        if self._view == "list":
            self._on_create()

    def action_edit_type(self) -> None:
        if self._view == "list":
            self._on_edit()

    def action_delete_type(self) -> None:
        if self._view == "list":
            self._on_delete()

    def action_refresh_types(self) -> None:
        if self._view == "list":
            self._on_refresh()

    def action_back_or_close(self) -> None:
        if self._view == "form":
            self._on_cancel()
        else:
            self.dismiss(None)


def open_subagent_types_manager(host: Any) -> None:
    if not hasattr(host, "push_screen"):
        raise RuntimeError("Sub-agent types manager requires TUI (push_screen)")
    host.push_screen(SubagentTypesManagerScreen(host))