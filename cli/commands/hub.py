"""Install skills from ClawHub, Claude marketplaces, skills.sh, git, and local bundles."""

from __future__ import annotations

from typing import Optional

import typer
from pathlib import Path

from cli.core import get_profile_manager
from cli.utils.rich_console import print_error, print_info, print_success, print_table, print_warning
from core.hub import SkillImporter
from core.hub.clawhub import ClawHubClient
from core.hub.claude_marketplace import MARKETPLACES, list_plugins, search_plugins
from core.hub.claude_mcp import merge_into_profile_servers
from core.hub.hermes_hub import list_hermes_skills, search_hermes_skills
from core.hub.skills_sh import search_skills_sh
from core.hub.autoupdate import run_hub_autoupdate, suggested_cron_line
from core.hub.updates import check_hub_updates
from core.hub.interactive import run_interactive_hub
from core.hub.slash_registry import rebuild_slash_registry

app = typer.Typer(help="Discover and install skills from external catalogs")


def _assign_skills_to_agents(
    ctx: typer.Context,
    skill_names: list[str],
    agents_csv: str | None,
) -> None:
    if not agents_csv or not skill_names:
        return
    from core.skills.assignments import apply_skills_to_agent_slots, known_agent_slots

    profile = ctx.obj.get("profile", "default")
    manager = get_profile_manager()
    config = ctx.obj["config"]
    slots = known_agent_slots(
        getattr(config, "skill_assignments", None),
        getattr(config, "agent_models", None),
    )
    requested = [a.strip() for a in agents_csv.split(",") if a.strip()]
    bad = [a for a in requested if a not in slots]
    if bad:
        print_warning(f"Unknown agent slot(s) ignored: {', '.join(bad)}")
    used = apply_skills_to_agent_slots(config, profile, manager, skill_names, agents_csv)
    if used:
        print_success(f"Assigned skill(s) to: {', '.join(used)}")


def _apply_mcp(ctx: typer.Context, servers: dict, plugin_name: str) -> int:
    if not servers:
        return 0
    profile = ctx.obj["profile"]
    manager = get_profile_manager()
    config = ctx.obj["config"]
    merged = merge_into_profile_servers(
        dict(getattr(config, "mcp_servers", {}) or {}),
        plugin_name,
        servers,
    )
    config.mcp_servers = merged
    manager.save_profile(profile, config)
    return len(servers)


@app.command("search")
def hub_search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
    source: str = typer.Option(
        "clawhub",
        "--source",
        "-s",
        help="clawhub | skills-sh | hermes | claude-official | claude-code",
    ),
):
    """Search public skill catalogs."""
    try:
        if source == "clawhub":
            hits = ClawHubClient().search(query, limit=limit)
            if not hits:
                print_info(f"No results for '{query}'")
                return
            rows = [
                [h.slug, h.display_name[:40], (h.summary or "")[:55], h.version or "latest", h.owner_handle or ""]
                for h in hits
            ]
            print_table("ClawHub", ["Slug", "Name", "Summary", "Version", "Owner"], rows)
            print_info("Install: helix hub install <slug>")

        elif source == "skills-sh":
            hits = search_skills_sh(query, limit=limit)
            if not hits:
                print_info(f"No skills.sh hits for '{query}' (needs GitHub API, unauthenticated limits apply)")
                return
            rows = [[h.skill_name, h.repo, h.path[:50], h.install_spec] for h in hits]
            print_table("skills.sh (GitHub)", ["Skill", "Repo", "Path", "Install spec"], rows)
            print_info("Install: helix hub install <install spec>")

        elif source == "hermes":
            hits = search_hermes_skills(query, limit=limit) if query else list_hermes_skills(limit=limit)
            if not hits:
                print_info(f"No HermesHub skills for '{query or 'browse'}'")
                return
            rows = [[h.slug, h.category, (h.description or h.slug)[:55], h.install_spec] for h in hits]
            print_table("HermesHub (GitHub)", ["Slug", "Category", "Summary", "Install spec"], rows)
            print_info("Install: helix hub install hermes:<slug>")

        elif source in MARKETPLACES:
            hits = search_plugins(source, query, limit=limit)
            if not hits:
                print_info(f"No plugins matching '{query}' in {source}")
                return
            rows = [[p.name, p.category, (p.description or "")[:60]] for p in hits]
            print_table(f"Claude marketplace ({source})", ["Plugin", "Category", "Description"], rows)
            print_info(f"Install: helix hub install claude:<plugin>@{source}")

        else:
            print_error(
                f"Unknown source '{source}'. Use: clawhub, skills-sh, hermes, claude-official, claude-code"
            )
            raise typer.Exit(1)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e


@app.command("marketplaces")
def hub_marketplaces():
    """List known Claude Code marketplaces."""
    rows = [[k, v["repo"], v["marketplace"]] for k, v in MARKETPLACES.items()]
    print_table("Claude marketplaces", ["ID", "Repository", "Catalog path"], rows)
    print_info("Search: helix hub search QUERY -s claude-official")


@app.command("plugins")
def hub_plugins(
    marketplace: str = typer.Argument("claude-official", help="Marketplace id"),
    limit: int = typer.Option(25, "--limit", "-l"),
):
    """List plugins in a Claude marketplace."""
    try:
        plugins = list_plugins(marketplace)[:limit]
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    if not plugins:
        print_info("No plugins found")
        return
    rows = [[p.name, p.category, (p.description or "")[:70]] for p in plugins]
    print_table(f"Plugins in {marketplace}", ["Name", "Category", "Description"], rows)


@app.command("browse")
def hub_browse(
    ctx: typer.Context,
    source: str = typer.Option(
        "claude-official",
        "--source",
        "-s",
        help="Starting catalog: claude-official, claude-code, clawhub, skills-sh",
    ),
):
    """Interactive search, pick, and install (plugins and skills)."""
    run_interactive_hub(ctx, default_source=source, apply_mcp_fn=_apply_mcp)


@app.command("install")
def hub_install(
    ctx: typer.Context,
    spec: Optional[str] = typer.Argument(
        None,
        help="Omit for interactive picker, or: clawhub slug | claude:plugin@marketplace | git URL | path",
    ),
    as_name: str | None = typer.Option(None, "--as", help="Override Helix skill name"),
    no_flat: bool = typer.Option(False, "--no-flat", help="Skip flat .md copy in skills root"),
    with_mcp: bool = typer.Option(True, "--with-mcp/--no-mcp", help="Merge Claude plugin MCP into profile"),
    agents: Optional[str] = typer.Option(
        None,
        "--agents",
        help="Comma-separated agent slots that may use installed skill(s) (e.g. main,coder)",
    ),
):
    """Install a skill or Claude plugin into the active profile.

    Examples:
      helix hub install              # interactive browser
      helix hub browse               # same as install with no args
      helix hub install git
      helix hub install claude:github@claude-official
    """
    if not spec:
        run_interactive_hub(ctx, apply_mcp_fn=_apply_mcp)
        return

    config = ctx.obj["config"]
    importer = SkillImporter(Path(config.skills_dir))
    try:
        result = importer.install(spec, as_name=as_name, flat=not no_flat)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e

    print_success(f"Installed '{result.skill_name}' ({result.source}:{result.slug})")
    if result.skill_names:
        print_info(f"Skills: {', '.join(result.skill_names)}")
    if result.version:
        print_info(f"Version: {result.version}")
    print_info(f"Bundle: {result.bundle_dir}")

    if result.mcp_servers and with_mcp:
        n = _apply_mcp(ctx, result.mcp_servers, result.slug)
        print_success(f"Added {n} MCP server(s) from plugin (prefix claude-{result.slug}-*)")
    elif result.mcp_servers and not with_mcp:
        print_warning("Plugin includes MCP servers; re-run with --with-mcp to add them to profile")

    names = result.skill_names or [result.skill_name]
    _assign_skills_to_agents(ctx, names, agents)

    rebuild_slash_registry(Path(config.skills_dir))
    print_info("Slash registry updated (user-invocable skills → /skill-name)")


@app.command("check-updates")
def hub_check_updates(ctx: typer.Context):
    """List hub-installed ClawHub skills with a newer version available."""
    config = ctx.obj["config"]
    importer = SkillImporter(Path(config.skills_dir))
    updates = check_hub_updates(importer.lock)
    if not updates:
        print_info("No ClawHub updates detected (or only non-ClawHub entries installed)")
        return
    rows = [
        [
            u.entry_id,
            u.skill_name,
            u.installed_version or "—",
            u.latest_version,
            u.install_spec[:45],
        ]
        for u in updates
    ]
    print_table(
        f"Updates available ({len(updates)})",
        ["ID", "Skill", "Installed", "Latest", "Install spec"],
        rows,
    )
    print_info("Update all: helix hub update  ·  One entry: helix hub update <id>")


@app.command("update")
def hub_update(
    ctx: typer.Context,
    entry_id: str | None = typer.Argument(None, help="Lock entry id (default: all)"),
):
    """Re-install hub entries from hub-lock.json."""
    config = ctx.obj["config"]
    importer = SkillImporter(Path(config.skills_dir))
    if entry_id:
        entry = importer.lock.get(entry_id)
        if not entry:
            print_error(f"Unknown entry: {entry_id}")
            raise typer.Exit(1)
        spec = entry.install_spec or importer._entry_to_spec(entry)
        if not spec:
            print_error("Entry has no reinstall spec")
            raise typer.Exit(1)
        try:
            importer.install(spec)
            print_success(f"Updated {entry_id}")
        except Exception as e:
            print_error(str(e))
            raise typer.Exit(1) from e
        return

    outcomes = importer.update_all()
    ok, fail = 0, 0
    for eid, outcome in outcomes:
        if isinstance(outcome, Exception):
            print_error(f"{eid}: {outcome}")
            fail += 1
        else:
            print_success(f"{eid}: {outcome.skill_name}")
            ok += 1
    print_info(f"Done: {ok} updated, {fail} failed")


@app.command("list")
def hub_list(ctx: typer.Context):
    """List skills installed via helix hub."""
    config = ctx.obj["config"]
    importer = SkillImporter(Path(config.skills_dir))
    entries = importer.lock.list_entries()
    if not entries:
        print_info("No hub-installed skills (use helix hub install)")
        return
    rows = [
        [
            e.id,
            e.skill_name,
            e.source,
            e.slug,
            e.version or "",
            (e.install_spec or "")[:40],
        ]
        for e in entries
    ]
    print_table(
        "Hub installs",
        ["ID", "Skill", "Source", "Slug", "Version", "Install spec"],
        rows,
    )


@app.command("remove")
def hub_remove(
    ctx: typer.Context,
    entry_id: str = typer.Argument(..., help="Lock entry id from `helix hub list`"),
    keep_flat: bool = typer.Option(False, "--keep-flat", help="Keep flat .md copy in skills root"),
):
    """Remove a hub-installed skill (bundle + lockfile; optional flat .md)."""
    profile = ctx.obj.get("profile", "default")
    config = ctx.obj["config"]
    from core.hub.installed import remove_hub_install

    try:
        names = remove_hub_install(
            profile,
            config,
            entry_id,
            drop_flat=not keep_flat,
        )
    except KeyError:
        print_error(f"Unknown entry: {entry_id}")
        raise typer.Exit(1) from None
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e

    print_success(f"Removed {entry_id} (skills: {', '.join(names)})")


@app.command("autoupdate")
def hub_autoupdate(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Run even if interval not elapsed"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would update"),
    full: bool = typer.Option(False, "--full", help="Reinstall all lock entries (not only ClawHub bumps)"),
    enable: Optional[bool] = typer.Option(
        None,
        "--enable/--disable",
        help="Persist hub_auto_update in profile config",
    ),
    interval_hours: Optional[float] = typer.Option(
        None,
        "--interval",
        help="Hours between automatic runs (saved to profile if set)",
    ),
    show_cron: bool = typer.Option(False, "--cron", help="Print example crontab line"),
):
    """Update hub skills when enabled or due (ClawHub version checks by default)."""
    profile = ctx.obj.get("profile", "default")
    manager = get_profile_manager()
    config = ctx.obj["config"]

    if enable is not None:
        config.hub_auto_update = enable
    if interval_hours is not None:
        config.hub_auto_update_interval_hours = interval_hours
    if enable is not None or interval_hours is not None:
        manager.save_profile(profile, config)
        print_success("Hub autoupdate settings saved")

    if show_cron:
        print_info("Example crontab (daily 04:00):")
        print_info(suggested_cron_line(profile))
        return

    importer = SkillImporter(Path(config.skills_dir))
    result = run_hub_autoupdate(
        importer,
        enabled=getattr(config, "hub_auto_update", False) or force,
        interval_hours=float(getattr(config, "hub_auto_update_interval_hours", 24) or 24),
        force=force,
        dry_run=dry_run,
        full_reinstall=full,
    )

    if not result.ran:
        print_info(f"Skipped ({result.reason}). Enable: helix hub autoupdate --enable")
        return
    if result.updated:
        print_success(f"Updated: {', '.join(result.updated)}")
    if result.failed:
        print_warning(f"Failed: {', '.join(result.failed)}")
    if result.reason == "nothing_to_update":
        print_info("No ClawHub updates available")
    if result.reason == "dry_run":
        print_info(f"Would update: {', '.join(result.updated)}")


@app.command("slash-sync")
def hub_slash_sync(ctx: typer.Context):
    """Rebuild skill-slash.json from installed skills."""
    config = ctx.obj["config"]
    rebuild_slash_registry(Path(config.skills_dir))
    print_success("skill-slash.json updated")