"""Agent extension protocol — holix-sdk base + Holix middleware/settings hooks."""

from __future__ import annotations

from typing import Any

from holix_sdk.agent import (
    AgentExtension,
    AgentExtensionContext,
    SlashCommandSpec,
)
from holix_sdk.agent import (
    AgentExtensionBase as _SDKAgentExtensionBase,
)

from core.extensions.middleware import MiddlewareChain

__all__ = [
    "AgentExtension",
    "AgentExtensionBase",
    "AgentExtensionContext",
    "SlashCommandSpec",
]


class AgentExtensionBase(_SDKAgentExtensionBase):
    """Agent extension with tools, slash commands, middleware, and settings.

    Optional hooks (override as needed)::

        def default_settings(self) -> dict: ...
        def on_settings_loaded(self, settings: dict) -> None: ...
        def register_middleware(self, chain, agent) -> None: ...
    """

    settings: dict[str, Any] = {}

    def default_settings(self) -> dict[str, Any]:
        """Default settings written on first install (merged with user file)."""
        return {}

    def on_settings_loaded(self, settings: dict[str, Any]) -> None:
        """Called during agent init after settings are loaded for this extension."""
        self.settings = dict(settings or {})

    def register_middleware(self, chain: MiddlewareChain, agent: Any) -> None:
        """Register LLM middleware on the agent request chain."""
        return None
