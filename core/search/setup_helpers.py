"""Shared helpers for configuring web search providers."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from core.search.catalog import SEARCH_PROVIDERS
from core.search.config import VALID_STRATEGIES, SearchConfig, default_search_config
from core.search.engine import SearchEngine, set_search_config


def detect_search_env() -> dict[str, str]:
    """Return non-empty search-related env vars already loaded in the process."""
    out: dict[str, str] = {}
    for key in ("FIRECRAWL_API_KEY", "SEARXNG_BASE_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            out[key] = value
    return out


def default_providers_from_env(env: dict[str, str] | None = None) -> list[str]:
    """Suggest provider order from env credentials (firecrawl → searxng → duckduckgo)."""
    env = env if env is not None else detect_search_env()
    order: list[str] = []
    if env.get("FIRECRAWL_API_KEY"):
        order.append("firecrawl")
    if env.get("SEARXNG_BASE_URL"):
        order.append("searxng")
    if not order:
        order.append("duckduckgo")
    return order


def load_profile_search(profile: str) -> dict[str, Any]:
    from core.profile import get_profile_manager

    cfg = get_profile_manager().load_profile(profile)
    raw = getattr(cfg, "search", None) or {}
    return SearchConfig.from_dict(raw).to_profile_dict()


def save_profile_search(profile: str, search_dict: dict[str, Any]) -> None:
    from core.profile import get_profile_manager

    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    cfg.search = search_dict  # type: ignore[attr-defined]
    manager.save_profile(profile, cfg)


def build_search_config(
    provider_order: list[str],
    *,
    strategy: str = "first_success",
    env_values: dict[str, str] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a profile ``search`` block from chosen providers."""
    env_values = env_values or {}
    overrides = overrides or {}
    result = default_search_config()
    result["strategy"] = strategy if strategy in VALID_STRATEGIES else "first_success"
    result["providers"] = list(provider_order)

    for spec in SEARCH_PROVIDERS:
        block = dict(result.get(spec.key) or {})
        enabled = spec.key in provider_order
        block["enabled"] = enabled
        if enabled:
            for field, default in spec.defaults.items():
                block.setdefault(field, default)
            if spec.key == "firecrawl" and env_values.get("FIRECRAWL_API_KEY"):
                block["api_key"] = "${FIRECRAWL_API_KEY}"
            if spec.key == "searxng" and env_values.get("SEARXNG_BASE_URL"):
                block["base_url"] = "${SEARXNG_BASE_URL}"
            block.update(overrides.get(spec.key) or {})
        result[spec.key] = block
    return result


def search_already_configured(profile: str) -> bool:
    """True when profile has a non-default enabled provider setup."""
    sc = SearchConfig.from_dict(load_profile_search(profile))
    enabled = sc.enabled_providers()
    if not enabled:
        return False
    if enabled == ["duckduckgo"] and sc.provider_order == ["duckduckgo"]:
        return False
    return True


def _upsert_env_var(path, key: str, value: str) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if p.is_file():
        lines = p.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    p.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def maybe_store_search_secret(
    env_var: str,
    value: str,
    *,
    profile: str,
    store_to_global: bool = True,
) -> str:
    """Persist a raw secret to env and return a ${ENV} reference."""
    if not value or value.startswith("${"):
        return value or f"${{{env_var}}}"
    if store_to_global:
        from core.global_config import global_env_path

        path = global_env_path()
    else:
        from core.env_loader import ensure_profile_env_template

        path = ensure_profile_env_template(profile)
    _upsert_env_var(path, env_var, value)
    os.environ[env_var] = value
    return f"${{{env_var}}}"


async def run_search_test(query: str, search_dict: dict[str, Any], *, max_results: int = 2) -> str:
    set_search_config(search_dict)
    return await SearchEngine().search(query, max_results=max_results)
