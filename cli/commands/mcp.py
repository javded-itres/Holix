"""MCP server management commands (add/list/remove/assign/test/setup)."""

from __future__ import annotations

import asyncio
from typing import Any

import typer
from core.mcp.installer import build_config_from_popular, clone_or_update_git, install_from_git
from core.mcp.popular import get_popular_by_key, get_popular_list
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.core import get_profile_manager
from cli.utils.rich_console import print_error, print_info, print_success

app = typer.Typer(help="Manage MCP servers: install popular ones or from git, configure, assign to agents/subs")


def _get_config_and_manager(ctx: typer.Context):
    profile = ctx.obj.get("profile") if ctx.obj else None
    if not profile:
        profile = "default"
    manager = get_profile_manager()
    config = ctx.obj.get("config") if ctx.obj else manager.load_profile(profile)
    return profile, config, manager


def _save_mcp_server(profile: str, manager, config, name: str, data: dict[str, Any]) -> None:
    servers = dict(getattr(config, "mcp_servers", {}) or {})
    servers[name] = data
    config.mcp_servers = servers  # type: ignore[attr-defined]
    manager.save_profile(profile, config)


def _interactive_popular_install(profile: str, manager, config) -> None:
    """Show popular list and let user pick + configure one."""
    popular = get_popular_list()
    if not popular:
        print_error("No popular servers defined.")
        return

    console = Console()
    table = Table(title="Popular MCP Servers (easy one-click install)")
    table.add_column("#", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Category")
    table.add_column("Description")

    for i, p in enumerate(popular, 1):
        table.add_row(str(i), p.display_name, p.category, p.description[:70])

    console.print(table)
    console.print("[dim]Enter number, or 'git' for custom git repo, or 'q' to cancel.[/dim]")

    choice = Prompt.ask("Select", default="1")
    if choice.lower() in ("q", "quit", "cancel"):
        return
    if choice.lower() == "git":
        _interactive_git_install(profile, manager, config)
        return

    try:
        idx = int(choice) - 1
        pop = popular[idx]
    except (ValueError, IndexError):
        print_error("Invalid selection.")
        return

    print_info(f"Installing {pop.display_name}...")
    params: dict[str, str] = {}
    for key, prompt in pop.param_prompts.items():
        default = pop.default_params.get(key, "")
        val = Prompt.ask(prompt, default=default)
        if val:
            params[key] = val

    data = build_config_from_popular(pop, params)
    if pop.env:
        # Ask to fill env vars
        env = dict(pop.env)
        for k in list(env.keys()):
            if not env[k]:
                val = Prompt.ask(f"Value for env {k} (required for this server)", password=True, default="")
                if val:
                    env[k] = val
        data["env"] = env

    if pop.notes:
        print_info(pop.notes)

    # Test?
    if Confirm.ask("Test the server now?", default=True):
        try:
            asyncio.run(_test_mcp_server(pop.key, data))
            print_success("Test successful!")
        except Exception as e:
            print_error(f"Test failed: {e}")
            if not Confirm.ask("Save the config anyway?", default=True):
                return

    name = pop.key
    _save_mcp_server(profile, manager, config, name, data)
    print_success(f"Added '{name}' to profile {profile}. Use `helix mcp assign` to enable it for agents/subs.")


def _interactive_git_install(profile: str, manager, config) -> None:
    url = Prompt.ask("Git repository URL (https or git@)")
    if not url:
        return
    suggested = url.rstrip("/").split("/")[-1].removesuffix(".git")
    name = Prompt.ask("Local name for this MCP server", default=suggested)

    print_info(f"Cloning {url} ... (this may take a moment)")
    try:
        cloned = clone_or_update_git(url, name)  # we use the low-level to show path
        print_info(f"Cloned to {cloned}")
    except Exception as e:
        print_error(f"Clone failed: {e}")
        return

    # Use the smart installer
    data = install_from_git(url, suggested_name=name, auto_prepare_steps=True)

    print_info("Detected / proposed configuration:")
    console = Console()
    console.print_json(data=data)

    # Let user customize
    if Confirm.ask("Edit the command/args before saving?", default=True):
        cmd = Prompt.ask("Command", default=data.get("command", "node"))
        args_str = Prompt.ask("Args (space separated)", default=" ".join(data.get("args", [])))
        data["command"] = cmd
        data["args"] = args_str.strip().split() if args_str.strip() else []

        if Confirm.ask("Add or edit environment variables?", default=bool(data.get("env"))):
            env = data.get("env", {})
            while True:
                k = Prompt.ask("ENV KEY (empty to stop)", default="")
                if not k:
                    break
                v = Prompt.ask(f"Value for {k}")
                env[k] = v
            data["env"] = env

    # Optional test
    if Confirm.ask("Attempt to start and list tools (test)?", default=True):
        try:
            asyncio.run(_test_mcp_server(name, data))
            print_success("Test OK")
        except Exception as e:
            print_error(f"Test failed: {e}")
            if not Confirm.ask("Save anyway?", default=False):
                return

    _save_mcp_server(profile, manager, config, name, data)
    print_success(f"Saved git-based MCP '{name}' (cloned into ~/.helix/mcp-servers/{name}).")
    print_info("You may need to run additional setup steps inside the cloned directory (see _notes if present).")


@app.command("list")
def mcp_list(ctx: typer.Context):
    """List configured MCP servers."""
    profile, config, _ = _get_config_and_manager(ctx)
    servers = getattr(config, "mcp_servers", {}) or {}
    assignments = getattr(config, "mcp_assignments", {}) or {}

    if not servers:
        print_info("No MCP servers configured for this profile. Use `helix mcp add`.")
        return

    table = Table(title=f"MCP Servers — profile: {profile}")
    table.add_column("Name", style="cyan")
    table.add_column("Transport", style="magenta")
    table.add_column("Target", style="green")
    table.add_column("Assigned to")
    table.add_column("Risk")

    for name, data in servers.items():
        transport = data.get("transport", "stdio")
        target = data.get("command") or data.get("url") or "?"
        risk = data.get("default_risk_level", "medium")
        assigned = ", ".join(
            a for a, lst in assignments.items() if name in (lst or [])
        ) or "—"
        source = data.get("_source", "")
        if source:
            name_display = f"{name} [{source}]"
        else:
            name_display = name
        table.add_row(name_display, transport, str(target)[:40], assigned, risk)

    console = Console()
    console.print(table)


@app.command("add")
def mcp_add(ctx: typer.Context, name: str | None = typer.Argument(None, help="Server name (e.g. filesystem)")):
    """Advanced: manually configure an MCP server (stdio/sse).

    For popular ready-made servers (context7, filesystem, github, etc.) or git repos,
    prefer the much easier `helix mcp install` command.
    """
    profile, config, manager = _get_config_and_manager(ctx)
    servers = dict(getattr(config, "mcp_servers", {}) or {})

    if not name:
        name = Prompt.ask("MCP server name (slug)", default="filesystem")

    if name in servers:
        if not Confirm.ask(f"'{name}' already exists. Overwrite?", default=False):
            return

    transport = Prompt.ask("Transport", choices=["stdio", "sse"], default="stdio")

    data: dict[str, Any] = {"transport": transport}

    if transport == "stdio":
        cmd = Prompt.ask("Command (e.g. npx or python)")
        data["command"] = cmd
        args_str = Prompt.ask("Args (space separated, or leave empty)", default="")
        if args_str.strip():
            data["args"] = args_str.strip().split()
        # simple env
        if Confirm.ask("Add environment variables?", default=False):
            env = {}
            while True:
                k = Prompt.ask("ENV KEY (empty to finish)", default="")
                if not k:
                    break
                v = Prompt.ask(f"Value for {k}")
                env[k] = v
            if env:
                data["env"] = env
        cwd = Prompt.ask("Working dir (optional)", default="")
        if cwd:
            data["cwd"] = cwd
    else:
        url = Prompt.ask("SSE URL (e.g. http://localhost:3000/sse)")
        data["url"] = url

    risk = Prompt.ask("Default risk (for confirmation)", choices=["no", "low", "medium", "high"], default="medium")
    data["default_risk_level"] = risk

    # test?
    if Confirm.ask("Test connection now (list tools)?", default=True):
        try:
            asyncio.run(_test_mcp_server(name, data))
            print_success("Connection + tool discovery OK")
        except Exception as e:
            print_error(f"Test failed: {e}")
            if not Confirm.ask("Save anyway?", default=True):
                return

    servers[name] = data
    config.mcp_servers = servers  # type: ignore[attr-defined]
    manager.save_profile(profile, config)
    print_success(f"Saved MCP server '{name}' to profile {profile}")


async def _test_mcp_server(name: str, data: dict) -> None:
    from core.mcp.manager import MCPManager

    mgr = MCPManager({name: data})
    await mgr.connect_all()
    # Wait for slow first-run npx/uvx (esp. context7 key validation)
    try:
        await mgr.wait_ready([name], timeout=12.0)
    except Exception:
        pass
    adapters = mgr.get_tool_adapters([name])
    print_info(f"Discovered {len(adapters)} tools: {[a.name for a in adapters][:8]}")
    if not adapters:
        errs = getattr(mgr, "_last_errors", {})
        if name in errs:
            hint = ""
            if name == "filesystem":
                hint = (
                    "\n[dim]Filesystem MCP needs existing directories. "
                    "Re-run install and set allowed_paths to your project folder "
                    "(e.g. /Users/you/Develop/ITRES/Helix).[/dim]"
                )
            print_error(f"Server error for {name}: {errs[name]}{hint}")
            raise RuntimeError(errs[name])
    await mgr.disconnect_all()


@app.command("remove")
def mcp_remove(ctx: typer.Context, name: str = typer.Argument(None, help="Server name to remove (optional)")):
    """Remove a configured MCP server."""
    profile, config, manager = _get_config_and_manager(ctx)
    servers = dict(getattr(config, "mcp_servers", {}) or {})
    if not name:
        if not servers:
            print_info("No MCP servers to remove.")
            return
        console = Console()
        console.print("Current MCP servers:")
        for i, n in enumerate(servers.keys(), 1):
            console.print(f"  {i}. {n}")
        choice = Prompt.ask("Number or name to remove", default="")
        if choice.isdigit():
            idx = int(choice) - 1
            names = list(servers.keys())
            if 0 <= idx < len(names):
                name = names[idx]
            else:
                print_error("Invalid number")
                return
        else:
            name = choice
    if name not in servers:
        print_error(f"No such server: {name}")
        return
    if Confirm.ask(f"Remove '{name}'?", default=False):
        servers.pop(name, None)
        # also clean assignments
        assigns = dict(getattr(config, "mcp_assignments", {}) or {})
        for k, lst in list(assigns.items()):
            if name in lst:
                assigns[k] = [x for x in lst if x != name]
        config.mcp_servers = servers
        config.mcp_assignments = assigns
        manager.save_profile(profile, config)
        print_success(f"Removed {name}")


@app.command("test")
def mcp_test(ctx: typer.Context, name: str = typer.Argument(..., help="Server name")):
    """Connect to a configured server and list its tools."""
    profile, config, _ = _get_config_and_manager(ctx)
    servers = getattr(config, "mcp_servers", {}) or {}
    if name not in servers:
        print_error(f"Unknown server '{name}'")
        return
    try:
        asyncio.run(_test_mcp_server(name, servers[name]))
    except Exception as e:
        print_error(str(e))


@app.command("assign")
def mcp_assign(ctx: typer.Context):
    """Interactively assign MCP servers to agents / sub-agents (main, code-reviewer, researcher...)."""
    profile, config, manager = _get_config_and_manager(ctx)
    servers = list((getattr(config, "mcp_servers", {}) or {}).keys())
    if not servers:
        print_error("No MCP servers defined. Use `helix mcp add` first.")
        return

    assigns = dict(getattr(config, "mcp_assignments", {}) or {})

    known = ["main"] + list((getattr(config, "agent_models", {}) or {}).keys())
    # also common sub names
    from core.subagents.registry import list_available_subagents
    try:
        known += [s["name"] for s in list_available_subagents()]
    except Exception:
        pass
    known = sorted(set(known))

    print_info("Assign servers (comma list or empty for none). Known roles: " + ", ".join(known[:10]))

    for role in known:
        current = ", ".join(assigns.get(role, []))
        val = Prompt.ask(f"MCP servers for '{role}' (current: {current or '—'})", default=current)
        lst = [x.strip() for x in val.split(",") if x.strip()]
        if lst:
            assigns[role] = lst
        else:
            assigns.pop(role, None)

    config.mcp_assignments = assigns
    manager.save_profile(profile, config)
    print_success("Assignments saved")


@app.command("setup")
def mcp_setup(ctx: typer.Context):
    """Interactive wizard: add servers + assign to roles."""
    print_info("MCP Setup — servers will be saved to your profile in ~/.helix only.")
    # delegate to add + assign
    # simple loop
    while Confirm.ask("Add another MCP server?", default=True):
        mcp_add(ctx)
    if Confirm.ask("Configure assignments now?", default=True):
        mcp_assign(ctx)
    mcp_list(ctx)


@app.command("list-popular")
def mcp_list_popular():
    """Show the curated list of popular MCP servers that can be installed easily."""
    popular = get_popular_list()
    console = Console()
    table = Table(title="Popular MCP Servers (install with `helix mcp install`)")
    table.add_column("Key", style="cyan")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Description")
    table.add_column("Example command")
    table.add_column("Source")

    for p in popular:
        install_hint = " ".join(p.args_template)[:40] if p.args_template else (p.command or "")
        repo = p.repo_url or ""
        if repo:
            repo = repo[:40] + "…" if len(repo) > 43 else repo
        table.add_row(p.key, p.display_name, p.category, p.description[:50], install_hint, repo)

    console.print(table)
    console.print("\n[dim]Run `helix mcp install` (no arguments) for an interactive picker.[/dim]")


@app.command("install")
def mcp_install(
    ctx: typer.Context,
    what: str | None = typer.Argument(
        None,
        help="Popular key (e.g. filesystem, context7, github) OR a git URL. If omitted, shows interactive menu."
    )
):
    """Install a ready-made MCP server from the popular list or from a git repository.

    Examples:
      helix mcp install                 # interactive picker
      helix mcp install context7
      helix mcp install https://github.com/upstash/context7
    """
    profile, config, manager = _get_config_and_manager(ctx)

    if not what:
        # Interactive mode
        _interactive_popular_install(profile, manager, config)
        return

    # Direct key or git url
    if what.startswith(("http", "git@", "git+")):
        # git path
        print_info(f"Treating '{what}' as git repository...")
        data = install_from_git(what)
        name = what.rstrip("/").split("/")[-1].removesuffix(".git")
        name = Prompt.ask("Save under which name?", default=name)

        # Let user review
        console = Console()
        console.print_json(data=data)
        if Confirm.ask("Review/edit command before saving?", default=True):
            data["command"] = Prompt.ask("Command", default=data.get("command", "node"))
            args_str = Prompt.ask("Args (space sep)", default=" ".join(data.get("args", [])))
            data["args"] = args_str.strip().split() if args_str.strip() else []

        if Confirm.ask("Test now?", default=True):
            try:
                asyncio.run(_test_mcp_server(name, data))
            except Exception as e:
                print_error(f"Test: {e}")
                if not Confirm.ask("Save anyway?"):
                    return

        data["_source"] = "git"
        _save_mcp_server(profile, manager, config, name, data)
        print_success(f"Installed from git as '{name}'.")
        return

    # Popular key
    pop = get_popular_by_key(what)
    if not pop:
        print_error(f"Unknown popular server '{what}'. See `helix mcp list-popular` or use a git URL.")
        return

    # Reuse the interactive param logic but non-interactive as much as possible
    params = {}
    for key, prompt_text in pop.param_prompts.items():
        default = pop.default_params.get(key, "")
        # In direct mode we can take defaults or prompt
        val = Prompt.ask(prompt_text, default=default)
        if val:
            params[key] = val

    data = build_config_from_popular(pop, params)
    if pop.env:
        env = dict(pop.env)
        for k, v in list(env.items()):
            if not v:
                val = Prompt.ask(f"ENV {k} (press enter to skip for now)", default="")
                if val:
                    env[k] = val
        data["env"] = {k: v for k, v in env.items() if v}

    if pop.notes:
        print_info(pop.notes)

    if Confirm.ask(f"Test '{what}' now?", default=True):
        try:
            asyncio.run(_test_mcp_server(what, data))
            print_success("Test OK")
        except Exception as e:
            print_error(f"Test failed: {e}")
            if not Confirm.ask("Save the config anyway?", default=True):
                return

    data["_source"] = "popular"
    _save_mcp_server(profile, manager, config, what, data)
    print_success(f"Added popular server '{what}' to profile {profile}.")
