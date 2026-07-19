"""holix extensions — list and inspect installed extensions."""

from __future__ import annotations

import json
import sys

import typer

from cli.utils.rich_console import console, print_info

app = typer.Typer(help="Discover and inspect Holix extensions")


@app.command("list")
def extensions_list(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
    all_groups: bool = typer.Option(
        True,
        "--all/--host-only",
        help="Show host + agent + telegram entry points (default: all)",
    ),
) -> None:
    """List installed extensions visible to this Holix CLI environment."""
    from core.extensions.registry import (
        holix_install_hint,
        list_all_entrypoint_rows,
        list_extension_info,
    )

    if all_groups:
        rows = list_all_entrypoint_rows()
        if json_output:
            print_info(json.dumps(rows, indent=2, ensure_ascii=False))
            return
        if not rows:
            console.print("[yellow]No extensions found in this Holix environment.[/yellow]")
            console.print(holix_install_hint())
            return
        from rich.table import Table

        table = Table(title="Holix extensions")
        table.add_column("Name", style="cyan")
        table.add_column("Kind")
        table.add_column("Version")
        table.add_column("Source")
        table.add_column("Location")
        table.add_column("Status")
        for row in rows:
            table.add_row(
                str(row["name"]),
                str(row["kind"]),
                str(row["version"]),
                str(row.get("source") or "package"),
                str(row.get("entry_point") or row.get("package") or "—")[:48],
                str(row["status"]) + (f" ({row['error']})" if row.get("error") else ""),
            )
        console.print(table)
        console.print(f"[dim]Python: {sys.executable}[/dim]")
        from core.extensions.registry import holix_install_hint

        console.print(f"[dim]{holix_install_hint()}[/dim]")
        return

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
        console.print("[yellow]No host extensions installed.[/yellow]")
        console.print(holix_install_hint())
        return

    from rich.table import Table

    table = Table(title="Holix host extensions")
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
    console.print(f"[dim]Python: {sys.executable}[/dim]")


@app.command("agent-list")
def agent_extensions_list(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Include profile folder extensions"),
) -> None:
    """List holix.agent.extensions entry points and local folder extensions."""
    from core.env_loader import active_profile_name
    from core.extensions.agent_registry import clear_agent_extension_cache, discover_agent_extensions
    from core.extensions.registry import holix_install_hint

    prof = profile or active_profile_name()
    clear_agent_extension_cache()
    exts = discover_agent_extensions(prof)
    if json_output:
        payload = [
            {
                "name": e.name,
                "version": getattr(e, "version", "0.0.0"),
                "requires_holix": getattr(e, "requires_holix", ">=0.1.0"),
                "permissions": sorted(getattr(e, "permissions", frozenset()) or ()),
                "local_path": getattr(e, "_holix_local_path", None),
            }
            for e in exts
        ]
        print_info(json.dumps(payload, indent=2))
        return

    if not exts:
        console.print("[yellow]No agent extensions installed.[/yellow]")
        console.print(
            "Install a package or drop a folder into "
            f"[cyan]~/.holix/profiles/{prof}/extensions/<name>/[/cyan]"
        )
        console.print(holix_install_hint())
        return

    from rich.table import Table

    table = Table(title="Holix agent extensions")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Requires")
    table.add_column("Permissions")
    table.add_column("Source")

    for ext in exts:
        local = getattr(ext, "_holix_local_path", None)
        table.add_row(
            ext.name,
            getattr(ext, "version", "0.0.0"),
            getattr(ext, "requires_holix", ">=0.1.0"),
            ", ".join(sorted(getattr(ext, "permissions", frozenset()) or ())) or "—",
            "folder" if local else "package",
        )
    console.print(table)
    console.print(f"[dim]Python: {sys.executable}[/dim]")


@app.command("agent-create")
def agent_extension_create(
    name: str = typer.Argument(..., help="Extension id (a-z, digits, underscore)"),
    description: str = typer.Option("", "--description", "-d", help="Short description"),
    profile: str | None = typer.Option(None, "--profile", "-p"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing files"),
) -> None:
    """Scaffold a profile-local agent extension (no core changes)."""
    from core.env_loader import active_profile_name
    from core.extensions.scaffold import create_agent_extension_scaffold

    prof = profile or active_profile_name()
    try:
        result = create_agent_extension_scaffold(
            prof, name, description=description, overwrite=overwrite
        )
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Created[/green] {result['path']}")
    console.print(f"  agent.py: {result['agent_py']}")
    console.print(f"  slash:    {result['slash']}")
    console.print(f"  tool:     {result['tool']}")
    console.print(f"[dim]{result['note']}[/dim]")


@app.command("agent-disable")
def agent_extension_disable(
    name: str = typer.Argument(..., help="Extension name"),
    profile: str | None = typer.Option(None, "--profile", "-p"),
    reason: str = typer.Option("manual", "--reason", "-r"),
) -> None:
    """Disable an agent extension (safe kill-switch; survives bad code)."""
    from core.env_loader import active_profile_name
    from core.extensions.control import disable_extension

    prof = profile or active_profile_name()
    try:
        result = disable_extension(prof, name, reason=reason)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[yellow]Disabled[/yellow] {result['name']} → {result['control_file']}")
    console.print("[dim]Restart agent / gateway to unload.[/dim]")


@app.command("agent-enable")
def agent_extension_enable(
    name: str = typer.Argument(..., help="Extension name"),
    profile: str | None = typer.Option(None, "--profile", "-p"),
) -> None:
    """Re-enable a disabled/quarantined agent extension."""
    from core.env_loader import active_profile_name
    from core.extensions.control import enable_extension

    prof = profile or active_profile_name()
    try:
        result = enable_extension(prof, name)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Enabled[/green] {result['name']}")
    console.print("[dim]Restart agent / gateway to load.[/dim]")


@app.command("agent-control")
def agent_extension_control(
    profile: str | None = typer.Option(None, "--profile", "-p"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show disable/quarantine control file for agent extensions."""
    from core.env_loader import active_profile_name
    from core.extensions.control import control_path, list_local_agent_extension_folders, load_control

    prof = profile or active_profile_name()
    ctrl = load_control(prof)
    rows = list_local_agent_extension_folders(prof)
    if json_output:
        print_info(
            json.dumps(
                {
                    "profile": prof,
                    "control_file": str(control_path(prof)),
                    "control": ctrl,
                    "folders": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    console.print(f"[cyan]Control file:[/cyan] {control_path(prof)}")
    console.print(f"[cyan]Disabled:[/cyan] {', '.join(ctrl.get('disabled') or []) or '—'}")
    q = ctrl.get("quarantine") or {}
    if q:
        console.print("[cyan]Quarantine:[/cyan]")
        for k, v in q.items():
            console.print(f"  • {k}: {v}")
    else:
        console.print("[cyan]Quarantine:[/cyan] —")
    if rows:
        from rich.table import Table

        table = Table(title="Local agent extension folders")
        table.add_column("Name")
        table.add_column("Blocked")
        table.add_column("Reason")
        table.add_column("Path")
        for r in rows:
            table.add_row(
                r["name"],
                "yes" if r["blocked"] else "no",
                (r.get("block_reason") or "—")[:40],
                r["path"][:48],
            )
        console.print(table)
    console.print(
        "[dim]Emergency: HOLIX_AGENT_EXTENSIONS_OFF=1 · "
        "HOLIX_AGENT_EXTENSIONS_DISABLED=name1,name2[/dim]"
    )


@app.command("settings")
def extension_settings_cmd(
    name: str = typer.Argument(..., help="Extension name"),
    profile: str | None = typer.Option(None, "--profile", "-p"),
    set_kv: list[str] | None = typer.Option(
        None,
        "--set",
        help="Set key=value (repeatable)",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show or update extension settings YAML for the active profile.

    Note: some extensions (e.g. holix-telegram-billing) use **.env only** and ignore this file.
    """
    from core.env_loader import active_profile_name
    from core.extensions.settings import load_extension_settings, save_extension_settings

    prof = profile or active_profile_name()
    settings = load_extension_settings(prof, name)
    if set_kv:
        for item in set_kv:
            if "=" not in item:
                raise typer.BadParameter(f"expected key=value, got {item!r}")
            key, raw = item.split("=", 1)
            val: object = raw
            low = raw.lower()
            if low in {"true", "false"}:
                val = low == "true"
            else:
                try:
                    val = int(raw)
                except ValueError:
                    try:
                        val = float(raw)
                    except ValueError:
                        val = raw
            settings[key.strip()] = val
        path = save_extension_settings(prof, name, settings)
        print_info(f"Saved {path}")
    if json_output:
        print_info(json.dumps(settings, indent=2, ensure_ascii=False))
        return
    if not settings:
        console.print(f"[yellow]No YAML settings for extension '{name}' (profile {prof}).[/yellow]")
        console.print("[dim]Some extensions configure only via env (HOLIX_* in profile .env).[/dim]")
        return
    for key, value in settings.items():
        console.print(f"[cyan]{key}[/cyan] = {value}")


@app.command("which-python")
def extensions_which_python() -> None:
    """Show which Python/env this holix CLI uses (install extensions here)."""
    from core.extensions.registry import holix_install_hint

    console.print(f"[cyan]{sys.executable}[/cyan]")
    console.print(holix_install_hint())
