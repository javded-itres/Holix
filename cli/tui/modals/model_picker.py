"""TUI modal: switch LLM model at runtime (/models)."""

from __future__ import annotations

from typing import Any, Literal

from integrations.telegram.model_switch import (
    ModelChoice,
    apply_model_choice_sync,
    build_models_menu,
    choice_for_provider_model,
)
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static


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
        Binding("r", "refresh_models", "Refresh"),
        Binding("d", "set_default", "Default"),
    ]

    def __init__(self, host: Any) -> None:
        super().__init__()
        self._host = host
        self._menu = build_models_menu(getattr(host, "profile", "default"))
        self._view: Literal["root"] | tuple[Literal["provider"], int] = "root"
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical(id="model-picker-panel"):
            yield Header(show_clock=False)
            yield Static("", id="model-picker-title")
            yield Static("", id="model-picker-hint")
            yield ListView(id="model-picker-list")
            with Vertical(id="model-picker-actions"):
                yield Button("Refresh list", id="btn-model-refresh", variant="primary")
                yield Button("Set default", id="btn-model-default", variant="success")
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
                "[dim]Presets switch this chat · open a provider to refresh its list "
                "or set the default · Esc closes[/dim]"
            )
            if not self._menu.presets and not self._menu.providers:
                lv.mount(
                    ListItem(Static("[dim]No models in profile. Run: holix models setup[/dim]"))
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
                default = _short_model(prov.default_model or "—", 24)
                item = ListItem(
                    Static(
                        f"[bold]Provider[/bold] [cyan]{prov.name}[/cyan]  "
                        f"[dim]({n}) ★ {default} →[/dim]"
                    )
                )
                item._pick_kind = "provider"  # type: ignore[attr-defined]
                item._pick_index = i  # type: ignore[attr-defined]
                lv.mount(item)
            return

        _, prov_idx = self._view
        prov = self._menu.providers[prov_idx]
        title.update(f"[bold]{prov.name}[/bold]")
        default = prov.default_model or "—"
        hint.update(
            f"[dim]Enter — this chat · d — default (★ {_short_model(default, 28)}) · "
            "r — refresh from provider · Esc — back[/dim]"
        )
        for mid in prov.models:
            choice = choice_for_provider_model(prov.name, mid)
            mark = "● " if choice.slot_id == active else "○ "
            star = "★ " if mid == prov.default_model else ""
            item = ListItem(Static(f"{star}{mark}[cyan]{_short_model(mid)}[/cyan]"))
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

    def _provider_name(self) -> str | None:
        if self._view == "root":
            return None
        _, prov_idx = self._view
        providers = self._menu.providers
        if prov_idx < 0 or prov_idx >= len(providers):
            return None
        return providers[prov_idx].name

    def _highlighted_model(self) -> str | None:
        name = self._provider_name()
        if not name:
            return None
        _, prov_idx = self._view
        models = self._menu.providers[prov_idx].models
        lv = self.query_one("#model-picker-list", ListView)
        idx = lv.index
        if idx is None or idx < 0 or idx >= len(models):
            return None
        return models[idx]

    def _profile_config(self) -> Any:
        cfg = getattr(self._host, "config", None)
        if cfg is not None and getattr(cfg, "providers", None) is not None:
            return cfg
        from core.profile import ProfileManager

        return ProfileManager().load_profile(getattr(self._host, "profile", "default"))

    def _save(self, config: Any) -> None:
        from core.profile import ProfileManager

        ProfileManager().save_profile(getattr(self._host, "profile", "default"), config)
        host_cfg = getattr(self._host, "config", None)
        if host_cfg is not None and host_cfg is not config:
            for field in ("providers", "model", "default_provider", "agent_models"):
                if hasattr(config, field):
                    setattr(host_cfg, field, getattr(config, field))

    def _rebind_provider(self, name: str) -> None:
        self._menu = build_models_menu(getattr(self._host, "profile", "default"))
        for i, prov in enumerate(self._menu.providers):
            if prov.name == name:
                self._view = ("provider", i)
                self._render_list()
                return
        self._view = "root"
        self._render_list()

    def action_refresh_models(self) -> None:
        if self._view == "root":
            self.app.notify("Open a provider, then refresh its model list")
            return
        self.run_worker(self._refresh_models(), exclusive=True, group="model_refresh")

    async def _refresh_models(self) -> None:
        if self._busy:
            return
        name = self._provider_name()
        if not name:
            return
        self._busy = True
        try:
            from core.models.provider_models import refresh_provider_config

            self.app.notify(f"Refreshing {name}…")
            config = self._profile_config()
            stats = await refresh_provider_config(config, name)
            self._save(config)
            self._rebind_provider(name)
            extra = ""
            if stats.added or stats.removed:
                extra = f" (+{len(stats.added)}/-{len(stats.removed)})"
            self.app.notify(f"{name}: {len(stats.models)} models{extra}")
        except Exception as exc:
            self.app.notify(str(exc)[:160], severity="error")
        finally:
            self._busy = False

    def action_set_default(self) -> None:
        name = self._provider_name()
        model_id = self._highlighted_model()
        if not name or not model_id:
            self.app.notify("Highlight a model inside a provider, then set default")
            return
        try:
            from core.models.provider_models import set_provider_default_model

            config = self._profile_config()
            set_provider_default_model(config, name, model_id)
            self._save(config)
        except Exception as exc:
            self.app.notify(str(exc)[:160], severity="error")
            return
        self._rebind_provider(name)
        choice = choice_for_provider_model(name, model_id)
        try:
            label = apply_model_choice_sync(self._host, choice)
        except Exception as exc:
            self.app.notify(f"Default saved. Chat switch failed: {exc}"[:160], severity="error")
            return
        if hasattr(self._host, "transcript_write"):
            self._host.transcript_write(f"[dim]default model → {label}[/dim]")
        self.app.notify(f"Default {label}")

    @on(Button.Pressed, "#btn-model-refresh")
    def _on_refresh_btn(self) -> None:
        self.action_refresh_models()

    @on(Button.Pressed, "#btn-model-default")
    def _on_default_btn(self) -> None:
        self.action_set_default()

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
