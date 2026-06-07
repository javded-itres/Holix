"""Search provider configuration (profile + env)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.config_utils import resolve_env_refs

DEFAULT_STRATEGY = "first_success"
VALID_STRATEGIES = frozenset({"first_success", "merge"})


def default_search_config() -> dict[str, Any]:
    return {
        "strategy": DEFAULT_STRATEGY,
        "providers": ["duckduckgo"],
        "duckduckgo": {"enabled": True},
        "searxng": {"enabled": False, "base_url": ""},
        "firecrawl": {
            "enabled": False,
            "api_key": "${FIRECRAWL_API_KEY}",
            "base_url": "https://api.firecrawl.dev/v2",
            "country": "US",
        },
    }


@dataclass
class SearchConfig:
    """Resolved search settings for the active profile."""

    strategy: str = DEFAULT_STRATEGY
    provider_order: List[str] = field(default_factory=lambda: ["duckduckgo"])
    duckduckgo: Dict[str, Any] = field(default_factory=lambda: {"enabled": True})
    searxng: Dict[str, Any] = field(default_factory=dict)
    firecrawl: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SearchConfig:
        base = default_search_config()
        if not raw:
            return cls.from_dict(base)

        merged = {**base, **resolve_env_refs(raw)}
        strategy = str(merged.get("strategy") or DEFAULT_STRATEGY)
        if strategy not in VALID_STRATEGIES:
            strategy = DEFAULT_STRATEGY

        order = list(merged.get("providers") or ["duckduckgo"])
        # Keep only known providers, preserve order
        known = {"duckduckgo", "searxng", "firecrawl"}
        order = [p for p in order if p in known]
        if not order:
            order = ["duckduckgo"]

        return cls(
            strategy=strategy,
            provider_order=order,
            duckduckgo=dict(merged.get("duckduckgo") or {"enabled": True}),
            searxng=dict(merged.get("searxng") or {}),
            firecrawl=dict(merged.get("firecrawl") or {}),
        )

    def enabled_providers(self) -> List[str]:
        out: list[str] = []
        for name in self.provider_order:
            block = getattr(self, name, None)
            if isinstance(block, dict) and block.get("enabled"):
                out.append(name)
        return out

    def to_profile_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "providers": list(self.provider_order),
            "duckduckgo": dict(self.duckduckgo),
            "searxng": dict(self.searxng),
            "firecrawl": dict(self.firecrawl),
        }