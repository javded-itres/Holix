"""Multi-provider search orchestration."""

from __future__ import annotations

from typing import Any

from core.search.config import SearchConfig, default_search_config
from core.search.providers import PROVIDER_FN, SearchHit

_runtime_config: SearchConfig | None = None


def set_search_config(raw: dict[str, Any] | SearchConfig | None) -> None:
    """Called when agent/profile loads search settings."""
    global _runtime_config
    if isinstance(raw, SearchConfig):
        _runtime_config = raw
    elif raw:
        _runtime_config = SearchConfig.from_dict(raw)
    else:
        _runtime_config = SearchConfig.from_dict(default_search_config())


def get_search_config() -> SearchConfig:
    if _runtime_config is None:
        return SearchConfig.from_dict(default_search_config())
    return _runtime_config


class SearchEngine:
    """Query one or more configured search backends."""

    def __init__(self, config: SearchConfig | None = None):
        self._config = config or get_search_config()

    async def search(self, query: str, *, max_results: int = 5) -> str:
        enabled = self._config.enabled_providers()
        if not enabled:
            return (
                "Error: no search providers enabled. "
                "Run `holix search configure` to set up DuckDuckGo, SearXNG, or Firecrawl."
            )

        errors: list[str] = []
        collected: list[SearchHit] = []
        seen_urls: set[str] = set()

        for name in enabled:
            fn = PROVIDER_FN.get(name)
            if fn is None:
                continue
            cfg_block = getattr(self._config, name, {}) or {}
            try:
                hits = await fn(query, max_results=max_results, **cfg_block)
            except Exception as e:
                errors.append(f"{name}: {e}")
                continue

            if not hits:
                errors.append(f"{name}: no results")
                continue

            if self._config.strategy == "first_success":
                return self._format_hits(hits[:max_results], providers=[name], errors=errors)

            for hit in hits:
                key = (hit.url or hit.title).strip().lower()
                if key and key in seen_urls:
                    continue
                if key:
                    seen_urls.add(key)
                collected.append(hit)
                if len(collected) >= max_results:
                    break

            if len(collected) >= max_results:
                break

        if collected:
            providers = sorted({h.source for h in collected if h.source})
            return self._format_hits(collected[:max_results], providers=providers, errors=errors)

        detail = "; ".join(errors) if errors else "no results"
        return f"No results found for: {query}\n({detail})"

    @staticmethod
    def _format_hits(
        hits: list[SearchHit],
        *,
        providers: list[str],
        errors: list[str],
    ) -> str:
        if not hits:
            return "No results."

        lines = []
        if providers:
            lines.append(f"**Sources:** {', '.join(providers)}")
        for i, hit in enumerate(hits, 1):
            title = hit.title or "(no title)"
            lines.append(f"\n{i}. **{title}**")
            if hit.snippet:
                lines.append(f"   {hit.snippet[:400]}")
            if hit.url:
                lines.append(f"   URL: {hit.url}")
        if errors and len(providers) > 1:
            lines.append(f"\n_Note: some providers failed: {'; '.join(errors)}_")
        return "\n".join(lines)