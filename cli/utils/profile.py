"""Profile helpers for CLI messages and command resolution."""

from __future__ import annotations

import typer


def profile_cli_prefix(profile: str = "default") -> str:
    """``helix`` or ``helix -p <name>`` — omit flag for the default profile."""
    name = (profile or "default").strip() or "default"
    if name == "default":
        return "helix"
    return f"helix -p {name}"


def resolve_profile(ctx: typer.Context, override: str | None = None) -> str:
    """Active profile: explicit override, else global ``--profile`` from root callback."""
    from cli.core import resolve_active_profile_name

    if override and override.strip():
        return resolve_active_profile_name(override.strip())
    if ctx.obj and ctx.obj.get("profile"):
        return str(ctx.obj["profile"])
    return resolve_active_profile_name(None)