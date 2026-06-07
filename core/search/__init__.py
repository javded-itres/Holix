"""Web search providers (DuckDuckGo, SearXNG, Firecrawl)."""

from core.search.config import SearchConfig, default_search_config
from core.search.engine import SearchEngine

__all__ = ["SearchConfig", "SearchEngine", "default_search_config"]