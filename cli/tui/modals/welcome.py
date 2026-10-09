"""Welcome screen: Holix mark and continue-or-new session."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

HOLIX_LOGO = """\
██╗  ██╗ ██████╗ ██╗     ██╗██╗  ██╗
██║  ██║██╔═══██╗██║     ██║╚██╗██╔╝
███████║██║   ██║██║     ██║ ╚███╔╝
██╔══██║██║   ██║██║     ██║ ██╔██╗
██║  ██║╚██████╔╝███████╗██║██╔╝ ██╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝╚═╝  ╚═╝\
"""


def pick_last_tui_session(
    rows: list[dict[str, Any]],
    saved_id: str,
    *,
    busy: Any = None,
) -> dict[str, Any] | None:
    """Prefer the saved TUI chat if it has messages, else the newest free one.

    ``busy`` skips a conversation another live window already holds.
    """
    is_busy = busy if callable(busy) else (lambda _cid: False)
    tui_rows = [
        row
        for row in rows
        if str(row.get("conversation_id") or "").startswith("tui_")
        and int(row.get("message_count") or 0) > 0
        and not is_busy(str(row.get("conversation_id") or ""))
    ]
    for row in tui_rows:
        if row.get("conversation_id") == saved_id:
            return row
    return tui_rows[0] if tui_rows else None


class WelcomeScreen(ModalScreen[str]):
    """Returns ``continue`` or ``new``."""

    BINDINGS = [
        Binding("c", "choose('continue')", "Continue", show=False),
        Binding("n", "choose('new')", "New", show=False),
        Binding("escape", "choose('new')", "New", show=False),
    ]

    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
    }
    #welcome-panel {
        width: 62;
        height: auto;
        max-height: 24;
        border: solid $accent;
        background: $surface;
        padding: 1 2 1 2;
    }
    #welcome-logo {
        height: auto;
        color: $accent;
        text-style: bold;
    }
    #welcome-tag {
        height: 1;
        color: $text-muted;
        margin-bottom: 1;
    }
    #welcome-last {
        height: auto;
        margin-bottom: 1;
    }
    #welcome-actions {
        height: 3;
        align: center middle;
    }
    #welcome-actions Button {
        margin: 0 1;
        min-width: 24;
    }
    """

    def __init__(
        self,
        *,
        lang: str = "ru",
        last_label: str | None = None,
    ) -> None:
        super().__init__()
        self._lang = "ru" if lang == "ru" else "en"
        self._last_label = (last_label or "").strip() or None

    def compose(self) -> ComposeResult:
        ru = self._lang == "ru"
        with Vertical(id="welcome-panel"):
            yield Static(HOLIX_LOGO, id="welcome-logo")
            yield Static(
                "локальный агент" if ru else "local agent",
                id="welcome-tag",
            )
            if self._last_label:
                title = "Последняя сессия" if ru else "Last session"
                yield Static(f"{title}\n{self._last_label}", id="welcome-last")
            else:
                yield Static(
                    "Прошлых сессий нет." if ru else "No previous session.",
                    id="welcome-last",
                )
            with Horizontal(id="welcome-actions"):
                yield Button(
                    "Продолжить" if ru else "Continue",
                    id="continue",
                    variant="primary",
                    disabled=self._last_label is None,
                )
                yield Button(
                    "Новая сессия" if ru else "New session",
                    id="new",
                    variant="default",
                )

    def on_mount(self) -> None:
        target = "#continue" if self._last_label else "#new"
        try:
            self.query_one(target, Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        choice = event.button.id or "new"
        if choice == "continue" and self._last_label is None:
            choice = "new"
        self.dismiss(choice)

    def action_choose(self, choice: str) -> None:
        if choice == "continue" and self._last_label is None:
            choice = "new"
        self.dismiss(choice)
