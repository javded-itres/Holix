import aiohttp
from typing import List, Dict, Any
from core.tools.base import BaseTool


class WebSearchTool(BaseTool):
    """Tool for searching the web using DuckDuckGo."""

    def __init__(self):
        super().__init__()
        self.name = "web_search"
        self.description = "Search the web for information using DuckDuckGo. Returns top search results with titles, snippets, and URLs."
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
        """Search the web using DuckDuckGo API.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            Formatted search results
        """
        try:
            # DuckDuckGo Instant Answer API
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status != 200:
                        return f"Error: HTTP {response.status}"

                    data = await response.json()

            # Format results
            results = []

            # Abstract (main answer)
            if data.get("Abstract"):
                results.append(f"**Summary:** {data['Abstract']}")
                if data.get("AbstractURL"):
                    results.append(f"Source: {data['AbstractURL']}\n")

            # Related topics
            if data.get("RelatedTopics"):
                results.append("**Related Results:**")
                count = 0
                for topic in data["RelatedTopics"]:
                    if count >= max_results:
                        break

                    if isinstance(topic, dict) and "Text" in topic:
                        text = topic.get("Text", "")
                        url = topic.get("FirstURL", "")
                        if text:
                            results.append(f"\n{count + 1}. {text}")
                            if url:
                                results.append(f"   URL: {url}")
                            count += 1

            if not results:
                return f"No results found for: {query}"

            return "\n".join(results)

        except aiohttp.ClientError as e:
            return f"Error connecting to search API: {str(e)}"
        except Exception as e:
            return f"Error during web search: {str(e)}"


class WebFetchTool(BaseTool):
    """Tool for fetching content from a URL."""

    def __init__(self):
        super().__init__()
        self.name = "fetch_url"
        self.description = "Fetch and return the content from a URL. Useful for reading web pages, APIs, or downloading data."
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
            async with aiohttp.ClientSession() as session:
                if method.upper() == "GET":
                    async with session.get(url, timeout=15) as response:
                        status = response.status
                        content = await response.text()
                else:
                    async with session.post(url, timeout=15) as response:
                        status = response.status
                        content = await response.text()

                # Truncate if too long
                if len(content) > 5000:
                    content = content[:5000] + "\n\n... (truncated, total length: {})".format(len(content))

                return f"HTTP {status}\n\n{content}"

        except aiohttp.ClientError as e:
            return f"Error fetching URL: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"
