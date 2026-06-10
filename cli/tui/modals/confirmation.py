"""Dangerous-action confirmation modal screen."""

from __future__ import annotations

import json

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from cli.tui.shared.text_escape import format_confirmation_body


class ConfirmationModal(ModalScreen):
    """Modal dialog for dangerous action confirmation."""

    CSS = """
    ConfirmationModal {
        align: center middle;
    }

    #confirmation-dialog {
        background: $surface;
        border: thick $warning;
        padding: 1 2;
        width: 72;
        max-width: 90%;
        height: auto;
        max-height: 80%;
    }

    #confirmation-title {
        text-align: center;
        padding: 0 1;
        margin-bottom: 1;
    }

    #confirmation-body {
        padding: 0 1;
        margin-bottom: 1;
    }

    #confirmation-args {
        background: $surface-darken-1;
        padding: 0 1;
        margin-bottom: 1;
        max-height: 10;
        overflow-y: auto;
    }

    #confirmation-buttons {
        align: center middle;
        height: auto;
        padding: 1;
    }

    #confirmation-buttons Button {
        margin: 0 1;
        min-width: 16;
    }

    .risk-no { color: $success; }
    .risk-low { color: $text; }
    .risk-medium { color: $warning; }
    .risk-high { color: $error; text-style: bold; }
    """

    def __init__(
        self,
        tool_name: str,
        risk_level: str,
        reason: str,
        arguments: str,
        confirmation_id: str = "",
    ):
        super().__init__()
        self.tool_name = tool_name
        self.risk_level = risk_level
        self.reason = reason
        self.arguments = arguments
        self.confirmation_id = confirmation_id

    def compose(self) -> ComposeResult:
        risk_labels = {
            "no": "🟢 NO RISK",
            "low": "🔵 LOW RISK",
            "medium": "🟡 MEDIUM RISK",
            "high": "🔴 HIGH RISK",
        }
        risk_label = risk_labels.get(self.risk_level, f"⚠ {self.risk_level.upper()} RISK")

        with Container(id="confirmation-dialog"):
            yield Label(
                f"⚠ Confirmation Required\n{risk_label}",
                id="confirmation-title",
            )
            yield Label(
                format_confirmation_body(self.tool_name, self.reason),
                id="confirmation-body",
            )
            yield Static(self.arguments, id="confirmation-args", markup=False)
            with Horizontal(id="confirmation-buttons"):
                yield Button("[1] Allow once", variant="success", id="btn-allow-once")
                yield Button("[2] Allow session", variant="primary", id="btn-allow-session")
                yield Button("[3] Allow always", variant="primary", id="btn-allow-always")
                yield Button("[4] Deny", variant="error", id="btn-deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        choice_map = {
            "btn-allow-once": "allow_once",
            "btn-allow-session": "allow_session",
            "btn-allow-always": "allow_always",
            "btn-deny": "deny",
        }
        self.dismiss(choice_map.get(event.button.id, "deny"))

    def on_key(self, event) -> None:
        key_map = {
            "1": "allow_once",
            "2": "allow_session",
            "3": "allow_always",
            "4": "deny",
        }
        if event.key in key_map:
            self.dismiss(key_map[event.key])
            event.prevent_default()
            event.stop()
        elif event.key == "escape":
            self.dismiss("deny")
            event.prevent_default()
            event.stop()

    @classmethod
    def from_confirmation_event(cls, event) -> ConfirmationModal:
        try:
            args_str = json.dumps(event.arguments, indent=2, ensure_ascii=False)
            if len(args_str) > 500:
                args_str = args_str[:500] + "\n..."
        except Exception:
            args_str = str(event.arguments)[:500]

        return cls(
            tool_name=event.tool_name,
            risk_level=event.risk_level,
            reason=event.reason,
            arguments=args_str,
            confirmation_id=event.confirmation_id,
        )