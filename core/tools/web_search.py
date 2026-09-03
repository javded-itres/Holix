from core.search.content import fetch_page_content
from core.search.engine import SearchEngine
from core.tools.base import BaseTool


class WebSearchTool(BaseTool):
    """Tool for searching the web via configured providers."""

    def __init__(self):
        super().__init__()
        self.name = "web_search"
        self.description = (
            "Search the public web (DuckDuckGo, SearXNG, Firecrawl). "
            "Use only after this conversation's user task and prior tool results "
            "do not already answer. For «продолжай»/continue, stay on that task — "
            "do not start a new crawl. Prefer session_search for older turns."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, max_results: int = 5) -> str:
        """Search the web using profile-configured providers."""
        try:
            from core.runtime.agent_sessions import get_agent_session
            from core.tools.execution_context import get_profile_name

            live = get_agent_session(get_profile_name())
            engine = live.search if live is not None and hasattr(live, "search") else SearchEngine()
            return await engine.search(query, max_results=max_results)
        except Exception as e:
            return f"Error during web search: {str(e)}"


class WebFetchTool(BaseTool):
    """Tool for fetching content from a URL."""

    def __init__(self):
        super().__init__()
        self.name = "fetch_url"
        self.description = (
            "Fetch readable text from one URL (HTML→text; Firecrawl markdown when configured). "
            "Alias: web_fetch. The result includes `## Links on this page` from real hrefs — "
            "for site analysis follow only those links, never guess paths. "
            "If that list is long and the task is site/resource analysis, call "
            "research_site_pages instead of fetching the pages yourself. "
            "Do not refetch a URL already fetched in this conversation. "
            "After HTTP 404/403, stop that URL family."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET or POST)",
                    "enum": ["GET", "POST"],
                    "default": "GET",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, method: str = "GET") -> str:
        """Fetch content from a URL.

        Args:
            url: URL to fetch
            method: HTTP method

        Returns:
            Page content or error message
        """
        from core.tools.execution_context import get_conversation_id
        from core.tools.web_fetch_memory import (
            already_fetched_message,
            lookup_fetch,
            remember_fetch,
        )

        cid = get_conversation_id()
        prior = lookup_fetch(cid, url)
        if prior is not None:
            status, excerpt = prior
            return already_fetched_message(url, status, excerpt)
        try:
            status, content = await fetch_page_content(url, method=method)
            remember_fetch(cid, url, int(status), str(content or ""))
            return f"HTTP {status}\n\n{content}"
        except Exception as e:
            return f"Error fetching URL: {str(e)}"
