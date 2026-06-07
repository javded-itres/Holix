from typing import List, Dict, Any

from core.search.content import fetch_page_content
from core.search.engine import SearchEngine
from core.tools.base import BaseTool


class WebSearchTool(BaseTool):
    """Tool for searching the web via configured providers."""

    def __init__(self):
        super().__init__()
        self.name = "web_search"
        self.description = (
            "Search the web for information. Uses configured providers "
            "(DuckDuckGo, SearXNG, Firecrawl). Returns titles, snippets, and URLs."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }

    async def execute(self, query: str, max_results: int = 5) -> str:
        """Search the web using profile-configured providers."""
        try:
            engine = SearchEngine()
            return await engine.search(query, max_results=max_results)
        except Exception as e:
            return f"Error during web search: {str(e)}"


class WebFetchTool(BaseTool):
    """Tool for fetching content from a URL."""

    def __init__(self):
        super().__init__()
        self.name = "fetch_url"
        self.description = (
            "Fetch and return readable text from a URL. HTML pages are converted to plain text; "
            "when Firecrawl is configured, pages are scraped as markdown. "
            "Alias: web_fetch."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch"
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET or POST)",
                    "enum": ["GET", "POST"],
                    "default": "GET"
                }
            },
            "required": ["url"]
        }

    async def execute(self, url: str, method: str = "GET") -> str:
        """Fetch content from a URL.

        Args:
            url: URL to fetch
            method: HTTP method

        Returns:
            Page content or error message
        """
        try:
            status, content = await fetch_page_content(url, method=method)
            return f"HTTP {status}\n\n{content}"
        except Exception as e:
            return f"Error fetching URL: {str(e)}"
