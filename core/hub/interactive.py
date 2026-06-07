"""Interactive hub browser: search, pick, install."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.utils.rich_console import print_error, print_info, print_success, print_warning
from core.hub.catalog import (
    SOURCES,
    SOURCE_BY_KEY,
    CatalogRow,
    fetch_catalog_rows,
    parse_selection,
)
from core.hub.claude_marketplace import MARKETPLACES
from core.hub.importer import SkillImporter
from core.hub.slash_registry import rebuild_slash_registry


def _fetch_rows(source: str, query: str, *, limit: int = 20) -> list[CatalogRow]:
    if source in MARKETPLACES:
        print_info(f"Loading catalog '{source}'… (first run clones repo, may take a minute)")
    if source == "skills-sh" and not query.strip():
        print_warning("skills.sh requires a search query (e.g. 'react', 'kubernetes')")
    return fetch_catalog_rows(source, query, limit=limit)


def _print_results(rows: list[CatalogRow], *, title: str) -> None:
    console = Console()
    table = Table(title=title)
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Summary")
    table.add_column("MCP", style="dim", width=4)

    for i, row in enumerate(rows, 1):
        mcp = "yes" if row.has_mcp else ""
        table.add_row(str(i), row.title, row.category, row.summary, mcp)

    console.print(table)


def run_interactive_hub(
    ctx: Any,
    *,
    default_source: str = "claude-official",
    apply_mcp_fn: Callable[[Any, dict, str], int] | None = None,
) -> None:
    """Search → select → install loop for hub catalogs."""
    config = ctx.obj["config"]
    skills_dir = Path(config.skills_dir)
    importer = SkillImporter(skills_dir)
    console = Console()

    console.print("\n[bold]Helix Hub — interactive install[/bold]")
    console.print("[dim]Find a skill or Claude plugin, then install into the active profile.[/dim]\n")

    for key, sid, label in SOURCES:
        mark = " [cyan]*[/cyan]" if sid == default_source else ""
        console.print(f"  {key}. {label}{mark}")
    console.print("  q. Quit\n")

    src_choice = Prompt.ask("Catalog", default="1")
    if src_choice.lower() in ("q", "quit", "exit"):
        return

    if src_choice in SOURCE_BY_KEY:
        source = SOURCE_BY_KEY[src_choice]
    elif src_choice in MARKETPLACES:
        source = src_choice
    else:
        source = default_source

    while True:
        console.print(f"\n[bold]Catalog:[/bold] {source}")
        query = Prompt.ask(
            "Search (empty = top list, 'b' = change catalog, 'q' = quit)",
            default="",
        )
        if query.lower() in ("q", "quit", "exit"):
            return
        if query.lower() in ("b", "back"):
            src_choice = Prompt.ask("Catalog", default="1")
            if src_choice.lower() in ("q", "quit"):
                return
            if src_choice in SOURCE_BY_KEY:
                source = SOURCE_BY_KEY[src_choice]
            elif src_choice in MARKETPLACES:
                source = src_choice
            continue

        try:
            rows = _fetch_rows(source, query, limit=25)
        except Exception as e:
            print_error(f"Search failed: {e}")
            continue

        if not rows:
            print_info("No matches. Try another query.")
            continue

        _print_results(rows, title=f"Results ({len(rows)})")
        console.print(
            "[dim]Enter number to install (e.g. 3), several: 1,4,7 · r = search again · q = quit[/dim]"
        )

        choice = Prompt.ask("Select", default="")
        if choice.lower() in ("q", "quit", "exit"):
            return
        if choice.lower() in ("r", ""):
            continue

        picked = parse_selection(choice, len(rows))
        if not picked:
            print_error("Invalid selection.")
            continue

        with_mcp = True
        if source in MARKETPLACES:
            with_mcp = Confirm.ask("Install bundled MCP servers into profile?", default=True)

        installed_names: list[str] = []
        for idx in picked:
            row = rows[idx - 1]
            print_info(f"Installing {row.title}…")
            try:
                result = importer.install(row.install_spec)
            except Exception as e:
                print_error(f"{row.title}: {e}")
                continue

            print_success(f"Installed {result.skill_name} ({row.install_spec})")
            installed_names.extend(result.skill_names or [result.skill_name])
            if result.skill_names:
                print_info(f"  skills: {', '.join(result.skill_names)}")

            if result.mcp_servers and with_mcp and apply_mcp_fn:
                n = apply_mcp_fn(ctx, result.mcp_servers, result.slug)
                print_success(f"  MCP: added {n} server(s)")
            elif result.mcp_servers and not with_mcp:
                print_warning("  Plugin has MCP — skipped (--no-mcp)")

        rebuild_slash_registry(skills_dir)

        if installed_names and ctx is not None:
            from cli.core import get_profile_manager
            from core.skills.assignments import apply_skills_to_agent_slots

            if Confirm.ask(
                "Assign installed skill(s) to specific agents?",
                default=False,
            ):
                agents_csv = Prompt.ask(
                    "Agents (comma-separated: main, coder, researcher, …)",
                    default="main",
                )
                profile = ctx.obj.get("profile", "default")
                config = ctx.obj["config"]
                manager = get_profile_manager()
                used = apply_skills_to_agent_slots(
                    config,
                    profile,
                    manager,
                    list(dict.fromkeys(installed_names)),
                    agents_csv,
                )
                if used:
                    print_success(f"Assigned to: {', '.join(used)}")

        if not Confirm.ask("Install another from this list?", default=False):
            if not Confirm.ask("Search again?", default=True):
                return