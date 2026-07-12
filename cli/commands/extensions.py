"""holix extensions — list and inspect installed extensions."""

from __future__ import annotations

import json

import typer

from cli.utils.rich_console import console, print_info

app = typer.Typer(help="Discover and inspect Holix extensions")


@app.command("list")
def extensions_list(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
) -> None:
    """List extensions registered via holix.extensions entry points."""
    from core.extensions.registry import list_extension_info

    infos = list_extension_info()
    if json_output:
        payload = [
            {
                "name": i.name,
                "version": i.version,
                "requires_holix": i.requires_holix,
                "description": i.description,
                "capabilities": sorted(i.capabilities),
                "permissions": sorted(i.permissions),
                "package": i.package,
                "entry_point": i.entry_point,
                "manifest_id": i.manifest_id,
            }
            for i in infos
        ]
        print_info(json.dumps(payload, indent=2))
        return

    if not infos:
        console.print("[yellow]No extensions installed.[/yellow]")
        console.print("Install optional packages, e.g. [cyan]uv sync --extra demo[/cyan]")
        return

    from rich.table import Table

    table = Table(title="Holix extensions")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Requires")
    table.add_column("Capabilities")
    table.add_column("Package")

    for info in infos:
        table.add_row(
            info.name,
            info.version,
            info.requires_holix,
            ", ".join(sorted(info.capabilities)) or "—",
            info.package,
        )
    console.print(table)


@app.command("agent-list")
def agent_extensions_list(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
) -> None:
    """List holix.agent.extensions entry points."""
    from core.extensions.agent_registry import discover_agent_extensions

    exts = discover_agent_extensions()
    if json_output:
        payload = [
            {
                "name": e.name,
                "version": getattr(e, "version", "0.0.0"),
                "requires_holix": getattr(e, "requires_holix", ">=0.1.0"),
                "permissions": sorted(getattr(e, "permissions", frozenset()) or ()),
            }
            for e in exts
        ]
        print_info(json.dumps(payload, indent=2))
        return

    if not exts:
        console.print("[yellow]No agent extensions installed.[/yellow]")
        return

    from rich.table import Table

    table = Table(title="Holix agent extensions")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Requires")
    table.add_column("Permissions")

    for ext in exts:
        table.add_row(
            ext.name,
            getattr(ext, "version", "0.0.0"),
            getattr(ext, "requires_holix", ">=0.1.0"),
            ", ".join(sorted(getattr(ext, "permissions", frozenset()) or ())) or "—",
        )
    console.print(table)