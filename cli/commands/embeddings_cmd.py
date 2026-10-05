"""Optional text-similarity embeddings. Does not replace Holix memory search."""

from __future__ import annotations

from pathlib import Path

import typer
from core.decision.config import configure_embeddings, resolve_embeddings
from core.decision.skills import (
    EMBEDDINGS_SKILL,
    SkillSwitchError,
    apply_skill_switch,
    clear_skill,
    skill_installed,
)

from cli.core import get_profile_manager
from cli.utils.rich_console import print_error, print_info, print_success

app = typer.Typer(
    help="Optional text similarity (OpenAI /v1/embeddings or Ollama /api/embed). Off by default."
)


def _profile(ctx: typer.Context) -> tuple[str, object]:
    return ctx.obj["profile"], ctx.obj["config"]


def _skills_dir(config: object, profile: str) -> Path:
    raw = getattr(config, "skills_dir", None)
    if raw:
        return Path(str(raw))
    return get_profile_manager().get_profile_dir(profile) / "data" / "skills"


def _save(profile: str, config: object) -> None:
    get_profile_manager().save_profile(profile, config)


@app.command("status")
def embeddings_status(ctx: typer.Context) -> None:
    """Show the embeddings endpoint and optional skill. No secrets."""
    profile, config = _profile(ctx)
    resolved = resolve_embeddings(getattr(config, "embeddings", None) or {})
    installed = "on" if skill_installed(_skills_dir(config, profile), EMBEDDINGS_SKILL) else "off"
    key = "set" if resolved.api_key else ("not required" if resolved.api == "ollama" else "missing")
    print_info(f"profile: {profile}")
    print_info(f"enabled: {'yes' if resolved.enabled else 'no'}")
    print_info(f"api: {resolved.api}")
    print_info(f"model: {resolved.model or '—'}")
    print_info(f"base_url: {resolved.base_url or '—'}")
    print_info(f"key: {key}")
    print_info(f"skill {EMBEDDINGS_SKILL}: {installed}")


@app.command("use")
def embeddings_use(
    ctx: typer.Context,
    api: str = typer.Argument(..., help="off, openai, or ollama"),
    base_url: str | None = typer.Option(None, "--base-url"),
    model: str | None = typer.Option(None, "--model"),
) -> None:
    """Turn text similarity on or off. Does not change memory embeddings."""
    profile, config = _profile(ctx)
    current = getattr(config, "embeddings", None) or {}
    try:
        block = configure_embeddings(current, api, base_url=base_url, model=model)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    if not block.get("enabled"):
        block = clear_skill(block, _skills_dir(config, profile), EMBEDDINGS_SKILL)
    config.embeddings = block
    _save(profile, config)
    resolved = resolve_embeddings(block)
    print_success(f"Embeddings: {'on' if resolved.enabled else 'off'}")
    if resolved.enabled:
        print_info(f"api: {resolved.api}")
        print_info(f"model: {resolved.model}")
        print_info(f"base_url: {resolved.base_url}")
    print_info("Restart the agent to register text_similarity.")


@app.command("skills")
def embeddings_skills(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="on or off"),
    name: str = typer.Argument(EMBEDDINGS_SKILL, help="Optional skill name"),
) -> None:
    """Copy or remove the optional similarity skill. Requires embeddings to be on."""
    verb = action.strip().lower()
    if verb not in {"on", "off"}:
        print_error("action must be on or off")
        raise typer.Exit(1)
    if name != EMBEDDINGS_SKILL:
        print_error(f"This command only toggles {EMBEDDINGS_SKILL}.")
        raise typer.Exit(1)
    profile, config = _profile(ctx)
    block = dict(getattr(config, "embeddings", None) or {})
    enabled = resolve_embeddings(block).enabled
    try:
        updated = apply_skill_switch(
            block,
            block_enabled=enabled or verb == "off",
            skills_dir=_skills_dir(config, profile),
            name=name,
            enabled=verb == "on",
        )
    except SkillSwitchError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    config.embeddings = updated
    _save(profile, config)
    print_success(f"{name}: {verb}")
