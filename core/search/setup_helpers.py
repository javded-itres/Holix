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
    from cli.core import get_profile_manager

    cfg = get_profile_manager().load_profile(profile)
    raw = getattr(cfg, "search", None) or {}
    return SearchConfig.from_dict(raw).to_profile_dict()


def save_profile_search(profile: str, search_dict: dict[str, Any]) -> None:
    from cli.core import get_profile_manager

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


def configure_search_interactive(
    profile: str,
    *,
    lang: str = "en",
    allow_skip: bool = True,
    default_pick: str | None = None,
    title: str | None = None,
    body: str | None = None,
    test_query: str = "open source ai agents",
) -> bool:
    """Interactive provider picker; saves config to the profile."""
    from cli.installer.bootstrap_i18n import bt
    from cli.utils.rich_console import print_error, print_info, print_success, print_warning
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.table import Table

    console = Console()
    current = SearchConfig.from_dict(load_profile_search(profile))
    env_values = detect_search_env()

    if search_already_configured(profile):
        if not Confirm.ask(
            bt("search_reconfigure", lang, providers=", ".join(current.enabled_providers())),
            default=False,
        ):
            print_info(bt("search_keep", lang))
            return True

    if title or body:
        console.print()
        console.print(
            Panel.fit(
                f"[bold cyan]{title or bt('search_title', lang)}[/bold cyan]\n\n"
                f"{body or bt('search_body', lang)}",
                border_style="cyan",
            )
        )

    if env_values:
        hints = ", ".join(sorted(env_values))
        console.print(f"[dim]{bt('search_env_detected', lang, vars=hints)}[/dim]\n")

    table = Table()
    table.add_column("#", style="dim")
    table.add_column(bt("search_col_provider", lang), style="cyan")
    table.add_column(bt("search_col_details", lang))
    for i, spec in enumerate(SEARCH_PROVIDERS, 1):
        details = spec.description
        if spec.key == "firecrawl" and env_values.get("FIRECRAWL_API_KEY"):
            details = bt("search_firecrawl_ready", lang)
        elif spec.key == "searxng" and env_values.get("SEARXNG_BASE_URL"):
            details = bt("search_searxng_ready", lang, url=env_values["SEARXNG_BASE_URL"])
        table.add_row(str(i), spec.display_name, details)
    console.print(table)

    key_to_idx = {spec.key: i + 1 for i, spec in enumerate(SEARCH_PROVIDERS)}
    suggested = default_pick
    if suggested is None:
        indices = [
            str(key_to_idx[name])
            for name in default_providers_from_env(env_values)
            if name in key_to_idx
        ]
        suggested = ",".join(indices) if indices else "1"

    if allow_skip:
        console.print(f"  [cyan]0[/cyan]. {bt('search_skip_hint', lang)}")
    pick = Prompt.ask(
        bt("search_pick", lang),
        default=suggested,
    )
    if allow_skip and pick.strip() in {"0", ""}:
        print_info(bt("search_skipped", lang))
        return False

    indices: list[int] = []
    for part in pick.replace(" ", "").split(","):
        if not part:
            continue
        try:
            indices.append(int(part) - 1)
        except ValueError:
            print_error(bt("search_invalid_pick", lang, value=part))
            return False

    chosen: list[str] = []
    for idx in indices:
        if 0 <= idx < len(SEARCH_PROVIDERS):
            chosen.append(SEARCH_PROVIDERS[idx].key)
    if not chosen:
        print_error(bt("search_none_selected", lang))
        return False

    order_default = ",".join(chosen)
    order_pick = Prompt.ask(bt("search_order", lang), default=order_default)
    order = [p.strip() for p in order_pick.split(",") if p.strip() in chosen]
    for name in chosen:
        if name not in order:
            order.append(name)

    overrides: dict[str, dict[str, Any]] = {}
    for spec in SEARCH_PROVIDERS:
        if spec.key not in chosen or not spec.requires_config:
            continue
        block: dict[str, Any] = {}
        for field, prompt_key in spec.config_prompts.items():
            default = spec.defaults.get(field, "")
            if spec.key == "firecrawl" and field == "api_key":
                if env_values.get("FIRECRAWL_API_KEY"):
                    block[field] = "${FIRECRAWL_API_KEY}"
                    continue
                val = Prompt.ask(bt("search_firecrawl_key", lang), password=True, default="")
                if val:
                    block[field] = maybe_store_search_secret(
                        "FIRECRAWL_API_KEY",
                        val,
                        profile=profile,
                    )
                else:
                    block[field] = default
                continue
            if spec.key == "searxng" and field == "base_url":
                if env_values.get("SEARXNG_BASE_URL"):
                    block[field] = "${SEARXNG_BASE_URL}"
                    continue
                val = Prompt.ask(
                    bt("search_searxng_url", lang),
                    default=str(default or "http://127.0.0.1:8080"),
                )
                if val:
                    block[field] = maybe_store_search_secret(
                        "SEARXNG_BASE_URL",
                        val,
                        profile=profile,
                    )
                else:
                    block[field] = default
                continue
            if field in spec.secret_fields:
                val = Prompt.ask(prompt_key, password=True, default="")
                if val:
                    env_name = spec.env_hints.get(field, "")
                    if env_name:
                        block[field] = maybe_store_search_secret(env_name, val, profile=profile)
                    else:
                        block[field] = val
                else:
                    block[field] = default
            else:
                val = Prompt.ask(prompt_key, default=str(default or ""))
                block[field] = val or default
        overrides[spec.key] = block

    result = build_search_config(
        order,
        env_values=env_values,
        overrides=overrides,
    )

    if Confirm.ask(bt("search_test", lang), default=True):
        try:
            out = asyncio.run(run_search_test(test_query, result))
            console.print(out)
        except Exception as exc:
            print_warning(bt("search_test_failed", lang, err=exc))
            if not Confirm.ask(bt("search_save_anyway", lang), default=True):
                return False

    save_profile_search(profile, result)
    print_success(
        bt(
            "search_saved",
            lang,
            profile=profile,
            providers=", ".join(order),
        )
    )
    return True