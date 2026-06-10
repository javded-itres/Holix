"""Provider metadata for interactive setup."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchProviderSpec:
    key: str
    display_name: str
    description: str
    requires_config: bool = False
    config_prompts: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)
    secret_fields: list[str] = field(default_factory=list)
    env_hints: dict[str, str] = field(default_factory=dict)


SEARCH_PROVIDERS: list[SearchProviderSpec] = [
    SearchProviderSpec(
        key="duckduckgo",
        display_name="DuckDuckGo",
        description="Free instant-answer API (no API key, limited depth)",
        requires_config=False,
    ),
    SearchProviderSpec(
        key="searxng",
        display_name="SearXNG",
        description="Self-hosted meta-search (JSON API at your instance URL)",
        requires_config=True,
        config_prompts={
            "base_url": "SearXNG instance URL (e.g. http://127.0.0.1:8080)",
            "categories": "Categories (default: general)",
            "language": "Language code (optional, e.g. en, ru)",
        },
        defaults={
            "base_url": "http://127.0.0.1:8080",
            "categories": "general",
            "language": "",
            "safesearch": "0",
        },
        env_hints={"base_url": "SEARXNG_BASE_URL"},
    ),
    SearchProviderSpec(
        key="firecrawl",
        display_name="Firecrawl",
        description="Managed web search + optional page scrape (API key required)",
        requires_config=True,
        config_prompts={
            "base_url": "API base URL",
            "country": "ISO country code for geo results (e.g. US, DE, RU)",
        },
        defaults={
            "base_url": "https://api.firecrawl.dev/v2",
            "country": "US",
            "api_key": "${FIRECRAWL_API_KEY}",
        },
        secret_fields=["api_key"],
        env_hints={"api_key": "FIRECRAWL_API_KEY"},
    ),
]


def get_provider_spec(key: str) -> SearchProviderSpec | None:
    for spec in SEARCH_PROVIDERS:
        if spec.key == key:
            return spec
    return None