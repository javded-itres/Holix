"""Confirmation modal must not crash on tool args with brackets/quotes."""

from __future__ import annotations

import json

from cli.tui.modals.confirmation import ConfirmationModal
from cli.tui.shared.text_escape import escape_for_markup, format_confirmation_body


def test_escape_for_markup_brackets():
    assert escape_for_markup("[pip install]") == "\\[pip install]"


def test_format_confirmation_body_escapes_tool_name():
    body = format_confirmation_body("pip[install]", "run [dangerous]")
    assert "pip\\[install]" in body
    assert "run \\[dangerous]" in body


def test_from_confirmation_event_long_json_args():
    class Ev:
        tool_name = "Shell"
        risk_level = "high"
        reason = "pip install"
        confirmation_id = "x"
        arguments = {
            "command": 'python -c "packages=[\\"a==1\\"]"',
            "packages": ["fastapi==0.109.0"],
        }

    modal = ConfirmationModal.from_confirmation_event(Ev())
    assert "fastapi" in modal.arguments
    assert isinstance(modal.arguments, str)