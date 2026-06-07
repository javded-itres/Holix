"""
Plan Review Modal — DEPRECATED.

This modal is no longer used. Plans are now rendered as Markdown in the
chat log, and the user responds by typing in the chat input.

See core/plan_review/markdown_builder.py for the plan rendering logic,
and cli/tui/app.py._handle_plan_review_request() for the in-chat display.

This file is kept for backward compatibility but is not imported anywhere.
"""

from textual.screen import ModalScreen


class PlanReviewModal(ModalScreen):
    """DEPRECATED: Use in-chat plan review instead.

    Plans are now rendered as Markdown in the chat log and the user
    responds by typing 'да', 'нет', or free-form feedback.
    See app._handle_plan_review_request() and app._parse_review_response().
    """

    def __init__(self, **kwargs):
        super().__init__()
        # No-op: modal is not used anymore

    def compose(self):
        # No-op
        yield from []

    @classmethod
    def from_review_event(cls, event) -> "PlanReviewModal":
        """DEPRECATED: Use in-chat plan review instead."""
        return cls()