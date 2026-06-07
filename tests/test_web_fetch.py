"""Web fetch aliases and HTML extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.search.content import html_to_text
from core.subagents.base import ProcessMode, SubAgentConfig
from core.subagents.process import SubAgentProcessManager
from core.tools.registry import ToolRegistry


def test_html_to_text_strips_tags() -> None:
    raw = """
    <html><head><style>body{}</style><script>alert(1)</script></head>
    <body><h1>Title</h1><p>Hello <b>world</b>.</p></body></html>
    """
    text = html_to_text(raw)
    assert "Title" in text
    assert "Hello world" in text
    assert "<html" not in text
    assert "alert" not in text


def test_registry_web_fetch_alias() -> None:
    registry = ToolRegistry()
    registry.register_all()
    assert "fetch_url" in registry.tools
    assert "web_fetch" in registry.tools
    assert registry.tools["web_fetch"] is registry.tools["fetch_url"]


@pytest.mark.asyncio
async def test_web_researcher_gets_web_fetch_schema() -> None:
    from core.subagents.async_runner import AsyncSubAgentRunner
    from core.subagents.communication import AgentCommunicationBus

    parent = MagicMock()
    parent.tools = ToolRegistry()
    parent.tools.register_all()
    runner = AsyncSubAgentRunner(parent, AgentCommunicationBus().async_bus)
    config = SubAgentConfig(name="web_researcher", tools=["web_search", "web_fetch"])

    schemas = runner._get_tool_schemas(config)
    names = {s["function"]["name"] for s in schemas}
    assert names == {"web_search", "web_fetch"}


@pytest.mark.asyncio
async def test_process_spawn_passes_search_config() -> None:
    parent = MagicMock()
    parent.model = "smart"
    parent.config = MagicMock(
        base_url="http://localhost:4000/v1",
        api_key="sk-test",
        auto_allow_threshold="low",
        confirmation_timeout=300,
        non_interactive=False,
        mcp_servers={},
        skills_dir="",
        skill_assignments={},
        search={"strategy": "first_success", "providers": ["firecrawl"]},
    )
    parent.memory = None

    captured_args: list = []

    class FakeProcess:
        pid = 4242

        def __init__(self, target, args, daemon):
            captured_args.extend(args)

        def start(self):
            return None

    mgr = SubAgentProcessManager(parent)
    config = SubAgentConfig(name="web_researcher", process_mode=ProcessMode.PROCESS)

    with patch("core.subagents.process.multiprocessing.Process", FakeProcess):
        with patch("core.subagents.process.asyncio.create_task"):
            await mgr.run(config, "find docs")

    assert captured_args[-1] == {
        "strategy": "first_success",
        "providers": ["firecrawl"],
    }
    flattened = " ".join(str(a) for a in captured_args)
    assert "sk-test" not in flattened


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/metrics",
        "http://localhost/admin",
        "http://192.168.1.1/",
        "http://10.0.0.5/internal",
        "file:///etc/passwd",
    ],
)
async def test_fetch_page_content_blocks_ssrf(url: str) -> None:
    from core.search.content import fetch_page_content

    with pytest.raises(ValueError):
        await fetch_page_content(url)


@pytest.mark.asyncio
async def test_web_fetch_tool_reports_validation_error() -> None:
    from core.tools.web_search import WebFetchTool

    result = await WebFetchTool().execute(url="http://127.0.0.1:8000")
    assert "Error fetching URL" in result
    assert "not allowed" in result.lower() or "localhost" in result.lower()


@pytest.mark.asyncio
async def test_fetch_page_content_converts_html() -> None:
    from core.search.content import fetch_page_content

    html_body = "<html><body><p>Readable text</p></body></html>"

    class FakeResp:
        status = 200
        headers = {"Content-Type": "text/html"}

        async def text(self):
            return html_body

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        def get(self, *a, **k):
            return FakeResp()

    with patch("core.search.content.aiohttp.ClientSession", return_value=FakeSession()):
        status, content = await fetch_page_content("https://example.com")

    assert status == 200
    assert "Readable text" in content
    assert "<p>" not in content