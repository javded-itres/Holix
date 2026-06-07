"""TUI modal: switch LLM model at runtime (/models)."""

from __future__ import annotations

from typing import Any, Literal

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static

from integrations.telegram.model_switch import (
    ModelChoice,
    apply_model_choice_sync,
    build_models_menu,
    choice_for_provider_model,
)


def _short_model(name: str, max_len: int = 36) -> str:
    if len(name) <= max_len:
        return name
    return name[: max_len - 1] + "…"


class ModelPickerScreen(ModalScreen[None]):
    """Presets (main, agents) and per-provider model lists."""

    DEFAULT_CSS = """
    ModelPickerScreen {
        align: center middle;
    }
    #model-picker-panel {
        width: 88%;
        max-width: 100;
        height: 75%;
        border: solid $primary;
        background: $surface;
        padding: 0 1 1 1;
    }
    #model-picker-list {
        height: 1fr;
        border: solid $primary-darken-2;
        margin: 1 0;
    }
    #model-picker-hint {
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "back_or_close", "Back"),
        Binding("q", "back_or_close", "Back", show=False),
    ]

    def __init__(self, host: Any) -> None:
        super().__init__()
        self._host = host
        self._menu = build_models_menu(getattr(host, "profile", "default"))
        self._view: Literal["root"] | tuple[Literal["provider"], int] = "root"

    def compose(self) -> ComposeResult:
        with Vertical(id="model-picker-panel"):
            yield Header(show_clock=False)
            yield Static("", id="model-picker-title")
            yield Static("", id="model-picker-hint")
            yield ListView(id="model-picker-list")
            with Vertical(id="model-picker-actions"):
                yield Button("Back", id="btn-model-back", variant="default")
                yield Button("Close", id="btn-model-close")
            yield Footer()

    def on_mount(self) -> None:
        self.title = "Models"
        self._render_list()

    def _active_slot(self) -> str:
        return getattr(self._host, "active_model_slot", None) or getattr(
            getattr(self._host, "_session", None), "active_model_slot", "main"
        )

    def _render_list(self) -> None:
        title = self.query_one("#model-picker-title", Static)
        hint = self.query_one("#model-picker-hint", Static)
        lv = self.query_one("#model-picker-list", ListView)
        lv.clear()
        active = self._active_slot()

        if self._view == "root":
            title.update("[bold]Switch model[/bold]")
            hint.update(
                "[dim]Presets apply main/agent routing · providers list all models · "
                "Esc back/close[/dim]"
            )
            if not self._menu.presets and not self._menu.providers:
                lv.mount(
                    ListItem(
                        Static(
                            "[dim]No models in profile. Run: helix models setup[/dim]"
                        )
                    )
                )
                return
            for preset in self._menu.presets:
                mark = "● " if preset.slot_id == active else "○ "
                label = (
                    f"{mark}[cyan]{preset.label}[/cyan]  "
                    f"[dim]{preset.provider}/{_short_model(preset.model)}[/dim]"
                )
                item = ListItem(Static(label))
                item._pick_kind = "preset"  # type: ignore[attr-defined]
                item._pick_choice = preset  # type: ignore[attr-defined]
                lv.mount(item)
            for i, prov in enumerate(self._menu.providers):
                n = len(prov.models)
                item = ListItem(
                    Static(
                        f"[bold]Provider[/bold] [cyan]{prov.name}[/cyan]  "
                        f"[dim]({n} model{'s' if n != 1 else ''}) →[/dim]"
                    )
                )
                item._pick_kind = "provider"  # type: ignore[attr-defined]
                item._pick_index = i  # type: ignore[attr-defined]
                lv.mount(item)
            return

        _, prov_idx = self._view
        prov = self._menu.providers[prov_idx]
        title.update(f"[bold]{prov.name}[/bold]")
        hint.update("[dim]Pick a model · Esc to presets[/dim]")
        for mid in prov.models:
            choice = choice_for_provider_model(prov.name, mid)
            mark = "● " if choice.slot_id == active else "○ "
            item = ListItem(Static(f"{mark}[cyan]{_short_model(mid)}[/cyan]"))
            item._pick_kind = "model"  # type: ignore[attr-defined]
            item._pick_choice = choice  # type: ignore[attr-defined]
            lv.mount(item)

    def _apply_choice(self, choice: ModelChoice) -> None:
        try:
            label = apply_model_choice_sync(self._host, choice)
            if hasattr(self._host, "transcript_write"):
                self._host.transcript_write(f"[dim]model → {label}[/dim]")
            self.dismiss(None)
        except Exception as e:
            if hasattr(self._host, "transcript_write"):
                self._host.transcript_write(f"[red]Model switch failed: {e}[/red]")
            self.app.notify(str(e)[:120])

    @on(ListView.Selected, "#model-picker-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        item = event.item
        kind = getattr(item, "_pick_kind", None)
        if kind == "preset" or kind == "model":
            choice = getattr(item, "_pick_choice", None)
            if choice:
                self._apply_choice(choice)
            return
        if kind == "provider":
            idx = getattr(item, "_pick_index", None)
            if idx is not None:
                self._view = ("provider", int(idx))
                self._render_list()

    @on(Button.Pressed, "#btn-model-back")
    def _on_back_btn(self) -> None:
        self.action_back_or_close()

    @on(Button.Pressed, "#btn-model-close")
    def _on_close_btn(self) -> None:
        self.dismiss(None)

    def action_back_or_close(self) -> None:
        if self._view != "root":
            self._view = "root"
            self._render_list()
            return
        self.dismiss(None)


def open_model_picker(host: Any) -> None:
    """Open model picker if host supports Textual screens."""
    if not hasattr(host, "push_screen"):
        raise RuntimeError("Model picker requires TUI (push_screen)")
    host.push_screen(ModelPickerScreen(host))