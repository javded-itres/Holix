"""Site page research: URL selection and page_analyst fan-out."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from core.subagents.base import SubAgentResult
from core.subagents.registry import get_subagent_config
from core.subagents.spawn import prepare_subagent_config
from core.tools.lazy_schema import CORE_TOOL_NAMES
from core.tools.registry import ToolRegistry
from core.tools.site_research import (
    DEFAULT_MAX_PAGES,
    HARD_MAX_PAGES,
    PAGE_ANALYST_TYPE,
    ResearchSitePagesTool,
    coerce_url_list,
    page_analyst_task,
    select_research_urls,
)
from core.tools.slot_policy import PLAN_MODE_ALLOWED, tool_allowed_for_slot
from core.tools.subagents import register_subagent_tools
from core.tools.web_fetch_memory import remember_fetch, reset_fetch_memory


@pytest.fixture(autouse=True)
def _clear_fetch_memory():
    reset_fetch_memory()
    yield
    reset_fetch_memory()


def test_coerce_url_list_json_and_whitespace() -> None:
    assert coerce_url_list("https://a.example/x https://a.example/y") == [
        "https://a.example/x",
        "https://a.example/y",
    ]
    assert coerce_url_list('["https://a.example/x", "https://a.example/y"]') == [
        "https://a.example/x",
        "https://a.example/y",
    ]
    assert coerce_url_list([{"url": "https://a.example/x"}]) == ["https://a.example/x"]


def test_select_prefers_same_host_drops_assets_and_caps() -> None:
    urls = [
        "https://bot24u.ru/",
        "https://bot24u.ru/faq",
        "https://bot24u.ru/logo.png",
        "javascript:void(0)",
        "https://other.example/about",
        "https://bot24u.ru/pricing",
        "https://bot24u.ru/integrations",
        "https://bot24u.ru/docs",
        "https://bot24u.ru/blog",
        "https://bot24u.ru/contact",
        "https://bot24u.ru/extra",
    ]
    selected = select_research_urls(urls, max_pages=8)
    assert selected.preferred_host == "bot24u.ru"
    assert "https://bot24u.ru/logo.png" in selected.invalid
    assert all(item.startswith("https://bot24u.ru") for item in selected.to_fetch)
    assert "https://other.example/about" not in selected.to_fetch
    assert "https://other.example/about" in selected.capped
    assert len(selected.to_fetch) == 8
    assert "https://bot24u.ru/extra" in selected.to_fetch


def test_select_skips_already_fetched() -> None:
    remember_fetch("default", "https://bot24u.ru/", 200, "Home page")
    selected = select_research_urls(
        ["https://bot24u.ru/", "https://bot24u.ru/faq"],
        conversation_id="default",
    )
    assert selected.to_fetch == ["https://bot24u.ru/faq"]
    assert selected.cached[0]["url"] == "https://bot24u.ru/"
    assert selected.cached[0]["cached"] is True


def test_page_analyst_builtin_is_fetch_only() -> None:
    cfg = get_subagent_config("page_analyst")
    assert cfg.tools == ["fetch_url"]
    assert cfg.max_steps <= 16
    assert cfg.mcp_inherit is False
    assert "web_search" not in cfg.tools


def test_prepare_page_analyst_keeps_mcp_isolated() -> None:
    parent = SimpleNamespace(
        profile_name="default",
        subagent_default_process_mode="async",
        subagent_process_timeout=30.0,
        mcp_assignments={},
        agent_models={},
    )
    page = prepare_subagent_config("page_analyst", parent, instance_name="page_analyst-1")
    assert page.mcp_inherit is False
    assert "fetch_url" in page.tools
    assert "web_search" not in page.tools
    assert "tool_search" not in page.tools
    assert "ask_user" not in page.tools
    researcher = prepare_subagent_config("researcher", parent, instance_name="researcher")
    assert researcher.mcp_inherit is True
    assert "ask_user" in researcher.tools


def test_research_site_pages_slot_and_plan_mode() -> None:
    assert tool_allowed_for_slot("research_site_pages", "main")
    assert tool_allowed_for_slot("research_site_pages", "supervisor")
    assert not tool_allowed_for_slot("research_site_pages", "coder")
    assert "research_site_pages" in PLAN_MODE_ALLOWED


def test_register_research_site_pages_tool() -> None:
    parent = SimpleNamespace(config=SimpleNamespace(enable_subagents=True), subagents=None)
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    register_subagent_tools(registry, parent)
    assert "research_site_pages" in CORE_TOOL_NAMES
    assert "research_site_pages" in registry.tools
    assert "delegate_to_subagent" in registry.tools
    names = {schema["function"]["name"] for schema in registry.get_schemas()}
    assert "research_site_pages" in names


def test_page_analyst_task_pins_url() -> None:
    task = page_analyst_task("https://bot24u.ru/faq", "Find pricing")
    assert "https://bot24u.ru/faq" in task
    assert "Find pricing" in task
    assert "invent" in task.lower()


class _FakeMgr:
    def __init__(self, max_concurrent: int = 2) -> None:
        self.max_concurrent = max_concurrent
        self.active: list[SimpleNamespace] = []
        self.spawned_tasks: list[str] = []
        self.max_seen = 0
        self._n = 0

    def list_active(self) -> list[SimpleNamespace]:
        return list(self.active)

    async def spawn_typed(self, agent_type: str, task: str, **kwargs):
        assert agent_type == PAGE_ANALYST_TYPE
        assert kwargs.get("wait") is False
        if len(self.active) >= self.max_concurrent:
            raise RuntimeError(f"Sub-agent limit reached ({self.max_concurrent}).")
        self._n += 1
        handle = SimpleNamespace(name=f"page_analyst-{self._n}")
        self.active.append(handle)
        self.max_seen = max(self.max_seen, len(self.active))
        self.spawned_tasks.append(task)
        return handle, None

    async def wait_for(self, name: str, timeout: float | None = None) -> SubAgentResult:
        self.active = [h for h in self.active if h.name != name]
        return SubAgentResult(name=name, success=True, response=f"brief for {name}")


def _parent(mgr: _FakeMgr, *, enabled: bool = True, max_concurrent: int = 2):
    return SimpleNamespace(
        config=SimpleNamespace(
            enable_subagents=enabled,
            subagent_max_concurrent=max_concurrent,
            profile_name="default",
        ),
        subagents=mgr,
    )


@pytest.mark.asyncio
async def test_research_site_pages_waves_and_collects() -> None:
    mgr = _FakeMgr(max_concurrent=2)
    tool = ResearchSitePagesTool(_parent(mgr, max_concurrent=2))
    urls = [f"https://bot24u.ru/p{i}" for i in range(5)]
    raw = await tool.execute(urls=urls, goal="Analyze the product", max_pages=5)
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["mode"] == "page_analyst"
    assert len(payload["pages"]) == 5
    assert all(p["success"] for p in payload["pages"])
    assert mgr.max_seen <= 2
    assert len(mgr.spawned_tasks) == 5
    assert all("https://bot24u.ru/p" in t for t in mgr.spawned_tasks)


@pytest.mark.asyncio
async def test_research_site_pages_rejects_empty_goal() -> None:
    tool = ResearchSitePagesTool(_parent(_FakeMgr()))
    raw = await tool.execute(urls=["https://bot24u.ru/"], goal="  ")
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert "goal" in payload["error"]


@pytest.mark.asyncio
async def test_research_site_pages_uses_cached_without_spawn() -> None:
    remember_fetch("default", "https://bot24u.ru/faq", 200, "FAQ body")
    mgr = _FakeMgr()
    tool = ResearchSitePagesTool(_parent(mgr))
    raw = await tool.execute(
        urls=["https://bot24u.ru/faq"],
        goal="Summarize FAQ",
        max_pages=4,
    )
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["mode"] == "cached"
    assert payload["pages"][0]["cached"] is True
    assert mgr.spawned_tasks == []


@pytest.mark.asyncio
async def test_research_site_pages_direct_fetch_when_subagents_off() -> None:
    parent = _parent(_FakeMgr(), enabled=False)
    tool = ResearchSitePagesTool(parent)

    async def fake_fetch(url: str, **kwargs):
        return 200, f"body of {url}"

    with patch("core.search.content.fetch_page_content", side_effect=fake_fetch):
        raw = await tool.execute(
            urls=["https://bot24u.ru/a", "https://bot24u.ru/b"],
            goal="What is this product?",
        )
    payload = json.loads(raw)
    assert payload["mode"] == "direct_fetch"
    assert payload["pages"][0]["report"].startswith("body of")
    assert len(payload["pages"]) == 2


def test_hard_cap_constant() -> None:
    assert HARD_MAX_PAGES >= DEFAULT_MAX_PAGES
    assert HARD_MAX_PAGES <= 16
