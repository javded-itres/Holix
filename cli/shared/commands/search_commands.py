"""Shared /search slash commands."""

from __future__ import annotations

from typing import Any

from core.search.config import SearchConfig
from core.search.engine import SearchEngine, get_search_config, set_search_config


def _refresh_from_agent(host: Any) -> None:
    agent = getattr(host, "agent", None)
    if agent is None:
        return
    cfg = getattr(agent, "config", None)
    if cfg is None:
        return
    raw = getattr(cfg, "search", None)
    if raw:
        set_search_config(raw)


async def run_search_command(host: Any, command: str) -> None:
    cmd = command.strip().lower()
    parts = cmd.split()

    if cmd in ("/search", "/search list"):
        _refresh_from_agent(host)
        sc = get_search_config()
        enabled = sc.enabled_providers()
        lines = [
            "Search providers:",
            f"  strategy: {sc.strategy}",
            f"  order: {', '.join(sc.provider_order)}",
            f"  enabled: {', '.join(enabled) or '(none)'}",
        ]
        for name in ("duckduckgo", "searxng", "firecrawl"):
            block = getattr(sc, name, {}) or {}
            if name == "searxng" and block.get("base_url"):
                lines.append(f"  searxng url: {block.get('base_url')}")
            if name == "firecrawl" and block.get("enabled"):
                key = str(block.get("api_key") or "")
                lines.append(
                    f"  firecrawl: {'configured' if key else 'missing api_key'}"
                )
        lines.append("")
        lines.append("Configure: helix search configure  (or /search configure for hint)")
        host.transcript_write("\n".join(lines))
        return

    if cmd == "/search configure":
        host.transcript_write(
            "Interactive search setup:\n"
            "  helix search configure\n\n"
            "Providers: DuckDuckGo (free), SearXNG (self-hosted URL), Firecrawl (API key).\n"
            "After saving: helix gateway reload"
        )
        return

    if parts[0] == "/search" and len(parts) >= 2 and parts[1] == "test":
        query = command.split(maxsplit=2)[2] if len(parts) >= 3 else "test query"
        _refresh_from_agent(host)
        try:
            result = await SearchEngine().search(query, max_results=3)
            host.transcript_write(result[:4000])
        except Exception as e:
            host.transcript_write(f"search test failed: {e}")
        return

    host.transcript_write(
        "Search:\n"
        "  /search — list providers\n"
        "  /search configure — setup instructions\n"
        "  /search test <query> — test current config"
    )