"""Interactive configuration for web search providers."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import typer
from core.search.catalog import SEARCH_PROVIDERS
from core.search.config import VALID_STRATEGIES, SearchConfig, default_search_config
from core.search.engine import SearchEngine
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.core import get_profile_manager
from cli.utils.rich_console import print_error, print_info, print_success

app = typer.Typer(help="Configure web search providers (DuckDuckGo, SearXNG, Firecrawl)")


def _ctx_profile(ctx: typer.Context) -> str:
    if ctx.obj and ctx.obj.get("profile"):
        return ctx.obj["profile"]
    return "default"


def _load_search(profile: str) -> dict[str, Any]:
    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    raw = getattr(cfg, "search", None) or {}
    return SearchConfig.from_dict(raw).to_profile_dict()


def _save_search(profile: str, search_dict: dict[str, Any]) -> None:
    manager = get_profile_manager()
    cfg = manager.load_profile(profile)
    cfg.search = search_dict  # type: ignore[attr-defined]
    manager.save_profile(profile, cfg)


def _maybe_store_secret(env_var: str, value: str, *, profile: str = "default") -> str:
    """If user entered a raw secret, optionally persist to the profile .env."""
    if not value or value.startswith("${"):
        return value or f"${{{env_var}}}"
    from core.env_loader import ensure_profile_env_template

    path = ensure_profile_env_template(profile)
    if Confirm.ask(f"Save API key to {path} as {env_var}?", default=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if path.is_file():
            lines = path.read_text(encoding="utf-8").splitlines()
        prefix = f"{env_var}="
        lines = [ln for ln in lines if not ln.startswith(prefix)]
        lines.append(f"{env_var}={value}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.environ[env_var] = value
        print_success(f"Saved {env_var} to {path}")
        return f"${{{env_var}}}"
    return value


@app.command("list")
def search_list(ctx: typer.Context) -> None:
    """Show configured search providers for the active profile."""
    profile = _ctx_profile(ctx)
    data = _load_search(profile)
    sc = SearchConfig.from_dict(data)
    console = Console()
    table = Table(title=f"Search providers — profile '{profile}'")
    table.add_column("Provider", style="cyan")
    table.add_column("Enabled")
    table.add_column("Details")

    for spec in SEARCH_PROVIDERS:
        block = getattr(sc, spec.key, {}) or {}
        enabled = "yes" if block.get("enabled") else "no"
        details = ""
        if spec.key == "searxng" and block.get("base_url"):
            details = str(block.get("base_url"))
        elif spec.key == "firecrawl":
            key = str(block.get("api_key") or "")
            details = "api_key set" if key and not key.endswith("}") else "no api_key"
        table.add_row(spec.display_name, enabled, details)

    console.print(table)
    console.print(f"Strategy: [bold]{sc.strategy}[/bold]")
    console.print(f"Order: {', '.join(sc.provider_order)}")


@app.command("test")
def search_test(
    ctx: typer.Context,
    query: str = typer.Argument("helix ai agent", help="Test query"),
    max_results: int = typer.Option(3, "--max", "-n"),
) -> None:
    """Run a test search with the current profile configuration."""
    profile = _ctx_profile(ctx)
    data = _load_search(profile)
    from core.search.engine import set_search_config

    set_search_config(data)
    engine = SearchEngine()
    result = asyncio.run(engine.search(query, max_results=max_results))
    Console().print(result)


@app.command("configure")
def search_configure(ctx: typer.Context) -> None:
    """Interactively enable and configure search providers."""
    profile = _ctx_profile(ctx)
    console = Console()
    current = SearchConfig.from_dict(_load_search(profile))

    console.print("\n[bold]Web search setup[/bold]")
    console.print("Pick one or more providers. Holix tries them in the order you set.\n")

    table = Table()
    table.add_column("#", style="dim")
    table.add_column("Provider", style="cyan")
    table.add_column("Description")
    for i, spec in enumerate(SEARCH_PROVIDERS, 1):
        table.add_row(str(i), spec.display_name, spec.description)
    console.print(table)

    pick = Prompt.ask(
        "Enable providers (comma-separated numbers, e.g. 1,2,3)",
        default="1",
    )
    indices: list[int] = []
    for part in pick.replace(" ", "").split(","):
        if not part:
            continue
        try:
            indices.append(int(part) - 1)
        except ValueError:
            print_error(f"Invalid selection: {part}")
            raise typer.Exit(1)

    chosen: list[str] = []
    for idx in indices:
        if 0 <= idx < len(SEARCH_PROVIDERS):
            chosen.append(SEARCH_PROVIDERS[idx].key)
    if not chosen:
        print_error("No providers selected.")
        raise typer.Exit(1)

    strategy = Prompt.ask(
        "Strategy: first_success (stop at first hit) or merge (combine)",
        default=current.strategy if current.strategy in VALID_STRATEGIES else "first_success",
    )
    if strategy not in VALID_STRATEGIES:
        strategy = "first_success"

    order_pick = Prompt.ask(
        "Provider priority order (comma-separated names)",
        default=",".join(chosen),
    )
    order = [p.strip() for p in order_pick.split(",") if p.strip() in chosen]
    for name in chosen:
        if name not in order:
            order.append(name)

    result = default_search_config()
    result["strategy"] = strategy
    result["providers"] = order

    for spec in SEARCH_PROVIDERS:
        block = dict(result.get(spec.key) or {})
        block["enabled"] = spec.key in chosen
        if spec.key not in chosen:
            result[spec.key] = block
            continue

        if spec.requires_config:
            for field, prompt in spec.config_prompts.items():
                default = spec.defaults.get(field, block.get(field, ""))
                if field in spec.secret_fields:
                    val = Prompt.ask(prompt, password=True, default="")
                    if val:
                        env_name = spec.env_hints.get(field, "")
                        if env_name:
                            block[field] = _maybe_store_secret(env_name, val, profile=profile)
                        else:
                            block[field] = val
                    else:
                        block[field] = default
                else:
                    val = Prompt.ask(prompt, default=str(default or ""))
                    block[field] = val or default
            # Non-prompt defaults
            for field, default in spec.defaults.items():
                if field not in block:
                    block[field] = default
        else:
            block["enabled"] = True

        result[spec.key] = block

    if Confirm.ask("Test search now?", default=True):
        from core.search.engine import set_search_config

        set_search_config(result)
        try:
            out = asyncio.run(SearchEngine().search("open source ai agents", max_results=2))
            console.print(out)
        except Exception as e:
            print_error(f"Test failed: {e}")
            if not Confirm.ask("Save configuration anyway?", default=True):
                raise typer.Exit(1)

    _save_search(profile, result)
    print_success(f"Search configuration saved to profile '{profile}'.")
    print_info("Run `holix gateway reload` if the agent is already running.")


@app.callback(invoke_without_command=True)
def search_group(ctx: typer.Context) -> None:
    """Search provider management (use `holix search configure` for interactive setup)."""
    if ctx.invoked_subcommand is None:
        search_list(ctx)