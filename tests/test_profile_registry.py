"""ProfileAgentRegistry unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.gateway.profile_registry import ProfileAgentRegistry


@pytest.mark.asyncio
async def test_registry_lazy_init_and_reload() -> None:
    registry = ProfileAgentRegistry("default")
    mock_agent = MagicMock()
    mock_agent._initialized = True
    mock_container = AsyncMock()
    mock_container.close = AsyncMock()

    with patch(
        "core.gateway.profile_registry.ProfileAgentRegistry._create_entry",
        new_callable=AsyncMock,
    ) as create_entry:
        create_entry.return_value = type(
            "E",
            (),
            {
                "profile": "alice",
                "agent": mock_agent,
                "container": mock_container,
                "lock": __import__("asyncio").Lock(),
            },
        )()

        agent = await registry.get_agent("alice")
        assert agent is mock_agent
        assert "alice" in registry.list_loaded_profiles()

        result = await registry.reload("alice")
        assert result["status"] == "reloaded"
        mock_container.close.assert_awaited()