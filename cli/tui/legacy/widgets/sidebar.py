"""Sidebar with profile, tools, memory, sessions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Collapsible, ListView, Static


class HolixSidebar(Vertical):
    """Collapsible sidebar (width toggled by app)."""

    def __init__(self, profile: str, model: str, **kwargs) -> None:
        kwargs.setdefault("id", "sidebar")
        super().__init__(**kwargs)
        self._profile = profile
        self._model = model

    def compose(self) -> ComposeResult:
        yield Static("[bold]Profile[/bold]", classes="label")
        yield Static(self._profile, id="sidebar-profile", classes="value")

        yield Static("[bold]Model[/bold]", classes="label")
        yield Static(self._model, id="sidebar-model", classes="value")

        yield Static("[bold]Status[/bold]", classes="label")
        yield Static("Ready", id="sidebar-status", classes="value")

        yield Static("", id="sidebar-density", classes="density-indicator")

        yield Button("Clear Chat", id="btn-clear", variant="error")

        with Collapsible(title="Tools (…)", collapsed=False, id="tools-collapsible"):
            yield ListView(id="tools-list", classes="tools-list")

        with Collapsible(title="Memory", collapsed=False, id="memory-collapsible"):
            yield ListView(id="memory-list", classes="memory-list")

        with Collapsible(title="Sessions", collapsed=True, id="sessions-collapsible"):
            yield ListView(id="sessions-list", classes="sessions-list")

        with Collapsible(title="Skills", collapsed=True, id="skills-collapsible"):
            yield ListView(id="skills-list", classes="skills-list")

        with Collapsible(title="Profiles", collapsed=False, id="profiles-collapsible"):
            yield ListView(id="profiles-list", classes="profiles-list")

        with Collapsible(title="Exec Mode", collapsed=False, id="exec-mode-collapsible"):
            yield Static("⚡ ReAct", id="exec-mode-display", classes="value")

        with Collapsible(title="Sub-Agents", collapsed=True, id="subagents-collapsible"):
            yield ListView(id="subagents-list", classes="subagents-list")