"""Application ports (Dependency Inversion) for hot boundaries."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryPort(Protocol):
    async def initialize_db(self) -> None: ...

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int: ...

    async def get_conversation(
        self,
        conversation_id: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class SkillsPort(Protocol):
    async def initialize(self, *, defer_index: bool = False) -> None: ...


@runtime_checkable
class ToolsPort(Protocol):
    def get_openai_tools(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class ProfileStorePort(Protocol):
    def profile_exists(self, profile: str) -> bool: ...

    def load_profile(self, profile: str) -> Any: ...

    def save_profile(self, profile: str, config: Any, *, storage_mode: str = "sparse") -> None: ...

    def list_profiles(self) -> list[str]: ...


@runtime_checkable
class LlmClientFactoryPort(Protocol):
    def __call__(
        self,
        *,
        base_url: str,
        api_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any: ...
