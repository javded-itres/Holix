"""Unified modal / overlay coordinator for Holix TUI."""

from __future__ import annotations

from typing import Any

from cli.tui.modals.confirmation_presenter import ConfirmationPresenter
from cli.tui.modals.plan_review import PlanReviewPresenter


class ModalStack:
    """Single entry point for confirmation modals and in-chat plan review."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._active_kind: str | None = None
        self.confirmation = ConfirmationPresenter(app, self)
        self.plan_review = PlanReviewPresenter(app, self)

    @property
    def active_kind(self) -> str | None:
        return self._active_kind

    @property
    def has_active(self) -> bool:
        return self._active_kind is not None

    def set_active(self, kind: str | None) -> None:
        self._active_kind = kind