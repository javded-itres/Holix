"""Agent extension middleware chain + settings + local folder discovery."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.extensions.agent_base import AgentExtensionBase
from core.extensions.agent_registry import (
    clear_agent_extension_cache,
    register_agent_extensions,
)
from core.extensions.local_loader import discover_local_agent_extensions
from core.extensions.middleware import (
    LLMRequestContext,
    MiddlewareChain,
    install_llm_middleware,
)
from core.extensions.settings import (
    load_extension_settings,
    save_extension_settings,
)


@pytest.mark.asyncio
async def test_middleware_chain_order() -> None:
    order: list[str] = []

    class MW:
        def __init__(self, name: str) -> None:
            self.name = name

        async def process(self, ctx, call_next):
            order.append(f"{self.name}:before")
            result = await call_next()
            order.append(f"{self.name}:after")
            return result

    chain = MiddlewareChain()
    chain.add(MW("outer"))
    chain.add(MW("inner"))

    async def terminal():
        order.append("terminal")
        return "ok"

    ctx = LLMRequestContext(kwargs={"model": "m", "messages": []})
    result = await chain.run(ctx, terminal)
    assert result == "ok"
    assert order == [
        "outer:before",
        "inner:before",
        "terminal",
        "inner:after",
        "outer:after",
    ]
    assert ctx.duration_ms >= 0


@pytest.mark.asyncio
async def test_install_llm_middleware_proxies_create() -> None:
    calls: list[dict] = []

    class MW:
        name = "probe"

        async def process(self, ctx, call_next):
            calls.append({"model": ctx.model})
            return await call_next()

    chain = MiddlewareChain()
    chain.add(MW())

    inner_create = AsyncMock(return_value="resp")
    client = MagicMock()
    client.chat.completions.create = inner_create
    agent = SimpleNamespace(config=SimpleNamespace(profile_name="default"), extension_settings={})

    install_llm_middleware(client, chain, agent)
    out = await client.chat.completions.create(model="coder", messages=[{"role": "user", "content": "hi"}])
    assert out == "resp"
    assert calls == [{"model": "coder"}]
    inner_create.assert_awaited_once()


def test_settings_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    save_extension_settings("default", "stats", {"enabled": True, "path": "/tmp/x"})
    loaded = load_extension_settings("default", "stats", defaults={"enabled": False, "path": ""})
    assert loaded["enabled"] is True
    assert loaded["path"] == "/tmp/x"


def test_local_folder_extension_discovered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    # profile dir layout
    from core.profile.names import profile_dir_for_name

    root = profile_dir_for_name("default") / "extensions" / "local_stats"
    root.mkdir(parents=True)
    (root / "agent.py").write_text(
        """
from core.extensions.agent_base import AgentExtensionBase

class Ext(AgentExtensionBase):
    name = "local_stats"
    permissions = frozenset({"tools", "middleware"})
    def default_settings(self):
        return {"enabled": True, "collect": True}
    def register_middleware(self, chain, agent):
        class M:
            name = "local_stats_mw"
            async def process(self, ctx, call_next):
                return await call_next()
        chain.add(M())

def get_agent_extension():
    return Ext()
""",
        encoding="utf-8",
    )
    exts = discover_local_agent_extensions("default")
    names = {getattr(e, "name", "") for e in exts}
    assert "local_stats" in names


@pytest.mark.asyncio
async def test_register_agent_extensions_installs_middleware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    clear_agent_extension_cache()

    class StatsExt(AgentExtensionBase):
        name = "stats_test"
        version = "0.0.1"
        permissions = frozenset({"tools", "middleware"})

        def default_settings(self):
            return {"enabled": True}

        def register_middleware(self, chain, agent):
            class M:
                name = "stats_test_mw"
                hits = 0

                async def process(self, ctx, call_next):
                    type(self).hits += 1
                    return await call_next()

            chain.add(M())
            agent._mw_cls = M

    class FakeRegistry:
        def __init__(self):
            self.tools = {}

        def register(self, tool):
            self.tools[getattr(tool, "name", "t")] = tool

    create = AsyncMock(return_value="ok")
    client = MagicMock()
    client.chat.completions.create = create

    agent = SimpleNamespace(
        tools=FakeRegistry(),
        config=SimpleNamespace(profile_name="default", data_dir=str(tmp_path)),
        client=client,
    )

    with patch(
        "core.extensions.agent_registry.discover_agent_extensions",
        return_value=(StatsExt(),),
    ):
        names = register_agent_extensions(agent)
        assert "stats_test" in names
        assert len(agent.llm_middleware) == 1
        result = await agent.client.chat.completions.create(model="m", messages=[])
        assert result == "ok"
        assert agent._mw_cls.hits == 1

    clear_agent_extension_cache()


def test_disabled_extension_skips_middleware(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    clear_agent_extension_cache()
    save_extension_settings("default", "off_ext", {"enabled": False})

    class OffExt(AgentExtensionBase):
        name = "off_ext"
        permissions = frozenset({"tools", "middleware"})

        def default_settings(self):
            return {"enabled": True}

        def register_middleware(self, chain, agent):
            raise AssertionError("should not register when disabled")

    agent = SimpleNamespace(
        tools=SimpleNamespace(register=lambda t: None),
        config=SimpleNamespace(profile_name="default", data_dir=str(tmp_path)),
        client=MagicMock(),
    )
    with patch(
        "core.extensions.agent_registry.discover_agent_extensions",
        return_value=(OffExt(),),
    ):
        names = register_agent_extensions(agent)
        assert names == []
    clear_agent_extension_cache()
