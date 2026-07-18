"""Process gateway state (api.state) bind / clear / require helpers."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_bind_from_container_and_clear() -> None:
    from api import state
    from core.di.container import create_async_container, resolve_gateway_runtime_config

    state.clear()
    assert state.is_ready() is False

    container = create_async_container(resolve_gateway_runtime_config(), gateway=True)
    try:
        gw = await state.bind_from_container(container, host_profile_name="default")
        assert state.is_ready() is True
        assert gw.registry is state.registry
        assert gw.runs_store is state.runs_store
        assert gw.gateway_locks is not None
        assert state._agent_request_lock is gw.gateway_locks.agent_request
        snap = gw.snapshot()
        assert snap["ready"] is True
        assert snap["registry"] is True

        reg = state.require_registry()
        assert reg is gw.registry
    finally:
        state.clear()
        await container.close()

    assert state.is_ready() is False
    assert state.registry is None
    with pytest.raises(state.GatewayStateError):
        state.require_registry()


def test_monkeypatch_module_alias_is_ingested() -> None:
    from unittest.mock import MagicMock

    from api import state

    state.clear()
    mock = MagicMock(name="registry")
    state.registry = mock
    assert state.get().registry is mock
    state.clear()
