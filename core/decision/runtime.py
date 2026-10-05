"""Bind optional decision and embedding tools while a registry is built."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from core.decision.config import resolve_decision, resolve_embeddings

_flags: ContextVar[tuple[bool, bool] | None] = ContextVar(
    "holix_optional_model_tools", default=None
)


def _block(config: Any, key: str) -> Any:
    if config is None:
        return None
    if isinstance(config, dict):
        return config.get(key)
    return getattr(config, key, None)


@contextmanager
def bind_optional_tools(config: Any) -> Iterator[None]:
    decision_on = resolve_decision(_block(config, "decision")).enabled
    embeddings_on = resolve_embeddings(_block(config, "embeddings")).enabled
    token = _flags.set((decision_on, embeddings_on))
    try:
        yield
    finally:
        _flags.reset(token)


@contextmanager
def bind_optional_tools_for_profile(profile_name: str | None) -> Iterator[None]:
    config = None
    name = str(profile_name or "").strip()
    if name:
        try:
            from core.profile.service import ProfileManager

            config = ProfileManager().load_profile(name)
        except Exception:
            config = None
    with bind_optional_tools(config):
        yield


def optional_tools_enabled() -> tuple[bool, bool]:
    """``(decision, embeddings)``. Unbound registries stay off."""
    return _flags.get() or (False, False)
