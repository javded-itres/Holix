"""Skills management commands."""

from pathlib import Path

import typer
from core.hub.normalize import discover_skill_files, parse_skill_file
from core.skills.assignments import (
    agents_for_skill,
    assign_skill_to_agents,
    known_agent_slots,
    unassign_skill_from_agents,
)
from core.skills.manager import SkillsManager
from rich.prompt import Prompt

from cli.utils.rich_console import print_error, print_info, print_panel, print_success, print_table

app = typer.Typer(help="Manage Holix skills")


def _get_profile_manager(ctx: typer.Context):
    from cli.core import get_profile_manager

    profile = ctx.obj.get("profile", "default")
    manager = get_profile_manager()
    config = manager.load_profile(profile)
    return profile, config, manager


def _load_skill_names(skills_dir: Path) -> list[str]:
    names: set[str] = set()
    if not skills_dir.exists():
        return []
    for skill_file in discover_skill_files(skills_dir):
        parsed = parse_skill_file(skill_file)
        if parsed and parsed.get("name"):
            names.add(parsed["name"])
        else:
            if skill_file.name == "SKILL.md":
                names.add(skill_file.parent.name)
            else:
                names.add(skill_file.stem)
    return sorted(names)


@app.command("list")
def list_skills(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of skills to show"),
    agent: str | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Show only skills available to this agent/subagent (e.g. main, coder)",
    ),
):
    """List skills (optionally filtered by agent assignment)."""
    config = ctx.obj["config"]
    skills_dir = Path(config.skills_dir)

    if not skills_dir.exists():
        print_info("No skills directory found")
        return

    from core.di import resolve_runtime_config

    mgr = SkillsManager(resolve_runtime_config(config))
    mgr.load_all_skills()

    slot = agent or "main"
    assigns = getattr(config, "skill_assignments", None) or {}
    if assigns and agent and agent != "main":
        allowed = set(mgr.list_skill_names_for_agent(agent))
        hidden = [n for n in mgr.all_skills if n not in allowed]
        if hidden:
            print_info(
                f"Profile skill_assignments limits '{agent}' to {len(allowed)} skill(s). "
                f"Hidden from this agent: {', '.join(hidden[:8])}"
                + (" …" if len(hidden) > 8 else "")
                + ". Use `holix skills assign` to change."
            )
    rows = []
    for name in sorted(mgr.all_skills.keys())[: limit if not agent else 9999]:
        skill = mgr.all_skills[name]
        if agent and not mgr.is_allowed_for_agent(skill, slot):
            continue
        desc = (skill.get("description") or "")[:60]
        tags = ", ".join(skill.get("tags") or [])
        fm = skill.get("agents") or skill.get("agent_roles")
        fm_s = ", ".join(fm) if isinstance(fm, list) else (fm or "")
        assigned = ", ".join(agents_for_skill(getattr(config, "skill_assignments", {}) or {}, name))
        rows.append([name, desc, tags, fm_s or "—", assigned or "—"])
        if len(rows) >= limit:
            break

    title = f"Skills ({len(rows)} shown)"
    if agent:
        title += f" for agent '{agent}'"
    print_table(title, ["Name", "Description", "Tags", "YAML agents", "Profile assign"], rows)


@app.command("search")
def search_skills(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filter by agent slot"),
):
    """Search skills by query."""
    config = ctx.obj["config"]
    from core.di import resolve_runtime_config

    mgr = SkillsManager(resolve_runtime_config(config))
    results = mgr.get_relevant_skills(query, top_k=10, agent_slot=agent or "main")

    if results:
        rows = [[r.get("name", ""), (r.get("description") or "")[:60]] for r in results]
        print_table(f"Search Results ({len(results)})", ["Skill", "Description"], rows)
    else:
        print_info(f"No skills found matching '{query}'")


@app.command("show")
def show_skill(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Skill name"),
):
    """Show detailed information about a skill."""
    config = ctx.obj["config"]
    skills_dir = Path(config.skills_dir)

    skill = None
    flat = skills_dir / f"{name}.md"
    if flat.exists():
        skill = parse_skill_file(flat)
    if not skill:
        for sf in discover_skill_files(skills_dir):
            parsed = parse_skill_file(sf)
            if parsed and parsed.get("name") == name:
                skill = parsed
                break

    if not skill:
        print_error(f"Skill '{name}' not found")
        return

    assigns = agents_for_skill(getattr(config, "skill_assignments", {}) or {}, name)
    extra = ""
    if assigns:
        extra = f"\n\n[bold]Assigned agents (profile):[/bold] {', '.join(assigns)}"
    fm = skill.get("agents") or skill.get("agent_roles")
    if fm:
        extra += f"\n[bold]YAML agents:[/bold] {fm}"

    print_panel(skill.get("content", "") + extra, title=f"Skill: {name}", border_style="cyan")


@app.command("assign")
def skills_assign(
    ctx: typer.Context,
    skill_name: str | None = typer.Argument(None, help="Skill name (omit for interactive)"),
    agents: str | None = typer.Option(
        None,
        "--agents",
        help="Comma-separated agent slots (main, coder, researcher, ...)",
    ),
):
    """Assign a skill to specific agents/subagents (profile skill_assignments)."""
    profile, config, manager = _get_profile_manager(ctx)
    skills_dir = Path(config.skills_dir)
    known_skills = _load_skill_names(skills_dir)
    if not known_skills:
        print_error("No skills installed. Use `holix hub install` first.")
        raise typer.Exit(1)

    if not skill_name:
        print_info("Skills: " + ", ".join(known_skills[:20]))
        skill_name = Prompt.ask("Skill name")
    if skill_name not in known_skills:
        print_error(f"Unknown skill '{skill_name}'")
        raise typer.Exit(1)

    slots = known_agent_slots(
        getattr(config, "skill_assignments", None),
        getattr(config, "agent_models", None),
    )
    if agents:
        agent_list = [a.strip() for a in agents.split(",") if a.strip()]
    else:
        print_info("Known roles: " + ", ".join(slots))
        val = Prompt.ask(
            f"Agents for '{skill_name}' (comma-separated)",
            default=", ".join(
                agents_for_skill(getattr(config, "skill_assignments", {}) or {}, skill_name)
            ),
        )
        agent_list = [a.strip() for a in val.split(",") if a.strip()]

    bad = [a for a in agent_list if a not in slots]
    if bad:
        print_error(f"Unknown agent(s): {', '.join(bad)}. Known: {', '.join(slots)}")
        raise typer.Exit(1)

    assigns = dict(getattr(config, "skill_assignments", {}) or {})
    config.skill_assignments = assign_skill_to_agents(assigns, skill_name, agent_list)
    manager.save_profile(profile, config)
    print_success(f"Assigned '{skill_name}' to: {', '.join(agent_list)}")


@app.command("unassign")
def skills_unassign(
    ctx: typer.Context,
    skill_name: str = typer.Argument(..., help="Skill name"),
    agents: str | None = typer.Option(
        None,
        "--agents",
        help="Remove only from these agents (default: all)",
    ),
):
    """Remove a skill from agent allowlists."""
    profile, config, manager = _get_profile_manager(ctx)
    assigns = dict(getattr(config, "skill_assignments", {}) or {})
    agent_list = None
    if agents:
        agent_list = [a.strip() for a in agents.split(",") if a.strip()]
    config.skill_assignments = unassign_skill_from_agents(assigns, skill_name, agent_list)
    manager.save_profile(profile, config)
    print_success(f"Removed '{skill_name}' from assignments")


@app.command("agents")
def skills_agents(
    ctx: typer.Context,
    skill_name: str = typer.Argument(..., help="Skill name"),
):
    """Show which agents can use this skill (profile + YAML)."""
    profile, config, _ = _get_profile_manager(ctx)
    skills_dir = Path(config.skills_dir)
    skill = None
    for sf in discover_skill_files(skills_dir):
        parsed = parse_skill_file(sf)
        if parsed and parsed.get("name") == skill_name:
            skill = parsed
            break
    if not skill:
        print_error(f"Skill '{skill_name}' not found")
        raise typer.Exit(1)

    profile_agents = agents_for_skill(getattr(config, "skill_assignments", {}) or {}, skill_name)
    yaml_agents = skill.get("agents") or skill.get("agent_roles")
    lines = [f"[bold]{skill_name}[/bold]"]
    if yaml_agents:
        lines.append(f"YAML agents: {yaml_agents}")
    else:
        lines.append("YAML agents: (any — not restricted in skill file)")
    if profile_agents:
        lines.append(f"Profile assignments: {', '.join(profile_agents)}")
    elif getattr(config, "skill_assignments", None):
        lines.append("Profile assignments: (none — uses main fallback or all skills)")
    else:
        lines.append("Profile assignments: (none — all agents unless YAML restricts)")
    print_panel("\n".join(lines), title="Skill agents")


@app.command("assign-wizard")
def skills_assign_wizard(ctx: typer.Context):
    """Interactively configure skill_assignments per agent (like `holix mcp assign`)."""
    profile, config, manager = _get_profile_manager(ctx)
    skills_dir = Path(config.skills_dir)
    known_skills = _load_skill_names(skills_dir)
    if not known_skills:
        print_error("No skills installed.")
        raise typer.Exit(1)

    assigns = dict(getattr(config, "skill_assignments", {}) or {})
    slots = known_agent_slots(assigns, getattr(config, "agent_models", None))

    print_info("Comma-separated skill names per role (empty = no profile whitelist for that role).")
    print_info("Available skills: " + ", ".join(known_skills[:30]))

    for role in slots:
        current = ", ".join(assigns.get(role, []))
        val = Prompt.ask(f"Skills for '{role}' (current: {current or '—'})", default=current)
        lst = [x.strip() for x in val.split(",") if x.strip()]
        if lst:
            assigns[role] = lst
        else:
            assigns.pop(role, None)

    config.skill_assignments = assigns
    manager.save_profile(profile, config)
    print_success("skill_assignments saved")


@app.command("seed-bundled")
def skills_seed_bundled(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing bundled skills"),
):
    """Install packaged default skills (e.g. holix-cron) into the profile skills dir."""
    profile, config, manager = _get_profile_manager(ctx)
    from core.skills.bundled import ensure_bundled_assigned_to_main, seed_bundled_skills

    skills_dir = Path(config.skills_dir)
    installed = seed_bundled_skills(skills_dir, overwrite=force)
    assigns, assigned = ensure_bundled_assigned_to_main(
        getattr(config, "skill_assignments", None) or {},
        installed or None,
    )
    if assigned:
        config.skill_assignments = assigns
        manager.save_profile(profile, config)

    if not installed:
        print_info("No new bundled skills (already present or none packaged).")
        if assigned:
            print_success(f"Assigned to main agent: {', '.join(assigned)}")
        elif force:
            print_info(f"Skills dir: {skills_dir}")
        return
    print_success(f"Installed bundled skills: {', '.join(installed)}")
    if assigned:
        print_success(f"Assigned to main agent: {', '.join(assigned)}")
    print_info(f"Profile: {profile} · dir: {skills_dir}")
    print_info("Invoke in chat: /holix-cron  or ask about scheduling — skill is auto-retrieved.")


def _curator(config):
    from core.di import resolve_runtime_config
    from core.skills.curator import SkillCurator
    from core.skills.manager import SkillsManager

    mgr = SkillsManager(resolve_runtime_config(config))
    mgr.load_all_skills(defer_index=True)
    return SkillCurator(mgr)


@app.command("curator")
def skills_curator(ctx: typer.Context):
    """Show prune status: stale / archive candidates (no writes)."""
    config = ctx.obj["config"]
    report = _curator(config).status()
    print_info(
        f"curatable {report['curatable']}/{report['total']} · "
        f"stale≥{report['stale_after_days']}d archive≥{report['archive_after_days']}d"
    )
    if report["would_stale"]:
        print_info("would stale: " + ", ".join(report["would_stale"]))
    if report["would_archive"]:
        print_info("would archive: " + ", ".join(report["would_archive"]))
    if report["pinned"]:
        print_info("pinned: " + ", ".join(report["pinned"]))
    archived = report.get("archived") or []
    if archived:
        print_info(f"already archived: {len(archived)}")
    if not report["would_stale"] and not report["would_archive"]:
        print_success("Nothing to prune.")


@app.command("prune")
def skills_prune(
    ctx: typer.Context,
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview (default) or apply"),
    days: int | None = typer.Option(None, "--days", help="Override archive_after_days"),
):
    """Mark stale / archive unused agent-created skills. Bundled and pinned are skipped."""
    config = ctx.obj["config"]
    curator = _curator(config)
    if days:
        curator.archive_after_days = max(curator.stale_after_days, days)
    report = curator.run(dry_run=dry_run)
    verb = "would archive" if report["dry_run"] else "archived"
    print_info(f"stale: {', '.join(report['stale']) or '—'}")
    print_info(f"{verb}: {', '.join(report['archived']) or '—'}")
    if report["dry_run"]:
        print_info("Re-run with --apply to write changes.")


@app.command("restore")
def skills_restore(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Archived skill name"),
):
    """Move an archived skill back to the live skills dir."""
    config = ctx.obj["config"]
    try:
        path = _curator(config).restore(name)
    except (FileNotFoundError, ValueError) as exc:
        print_error(str(exc))
        raise typer.Exit(1)
    print_success(f"Restored {name} → {path}")


@app.command("pin")
def skills_pin(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Skill name"),
    unpin: bool = typer.Option(False, "--unpin", help="Allow curator to manage this skill again"),
):
    """Pin a skill so the curator will never stale/archive it."""
    config = ctx.obj["config"]
    try:
        _curator(config).pin(name, pinned=not unpin)
    except FileNotFoundError:
        print_error(f"Skill '{name}' not found")
        raise typer.Exit(1)
    print_success(("Unpinned " if unpin else "Pinned ") + name)


def _pending_store(config):
    from core.skills.proposal import SkillProposalStore

    return SkillProposalStore(config.skills_dir)


@app.command("pending")
def skills_pending(ctx: typer.Context):
    """List staged auto-skill proposals waiting for approval."""
    config = ctx.obj["config"]
    store = _pending_store(config)
    store.expire_stale()
    rows = store.list_pending()
    if not rows:
        print_info("No pending skill proposals.")
        return
    print_table(
        "Pending skill proposals",
        ["id", "action", "name", "description", "created"],
        [
            [
                r.get("id"),
                r.get("action"),
                r.get("name"),
                (r.get("description") or "")[:60],
                r.get("created_at"),
            ]
            for r in rows
        ],
    )


@app.command("approve")
def skills_approve(
    ctx: typer.Context,
    proposal_id: str = typer.Argument(..., help="Pending proposal id (psp-…)"),
    assign: str | None = typer.Option(
        None,
        "--assign",
        help="Comma-separated agent slots to assign after apply (default: none)",
    ),
):
    """Apply a staged skill proposal to the profile skills dir."""
    config = ctx.obj["config"]
    from core.di import resolve_runtime_config

    store = _pending_store(config)
    mgr = SkillsManager(resolve_runtime_config(config))
    mgr.load_all_skills(defer_index=True)
    slots = [a.strip() for a in (assign or "").split(",") if a.strip()]
    try:
        rec = store.approve(proposal_id, manager=mgr, assign_to=slots)
    except FileNotFoundError:
        print_error(f"Proposal '{proposal_id}' not found")
        raise typer.Exit(1)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1)
    print_success(
        f"{rec.get('action')} '{rec.get('name')}' → {rec.get('filepath') or rec.get('merged_into') or 'ok'}"
    )


@app.command("reject")
def skills_reject(
    ctx: typer.Context,
    proposal_id: str = typer.Argument(..., help="Pending proposal id (psp-…)"),
):
    """Drop a staged skill proposal without applying it."""
    config = ctx.obj["config"]
    try:
        rec = _pending_store(config).reject(proposal_id)
    except FileNotFoundError:
        print_error(f"Proposal '{proposal_id}' not found")
        raise typer.Exit(1)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1)
    print_success(f"Rejected {rec.get('name')} ({rec.get('id')})")
