"""Optional System One decision model (Jev, nimble, tev1, or a custom endpoint)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from core.decision.config import configure_decision, resolve_decision
from core.decision.gates import INTERNAL_FLAGS
from core.decision.internal import set_internal_flag, set_threshold
from core.decision.skills import (
    DECISION_SKILL,
    SkillSwitchError,
    apply_skill_switch,
    clear_skill,
    skill_installed,
)
from core.decision.systemone import probe_decision

from cli.core import get_profile_manager
from cli.utils.rich_console import print_error, print_info, print_success

app = typer.Typer(help="Optional System One decisions (Jev, nimble, tev1). Off by default.")


def _profile(ctx: typer.Context) -> tuple[str, object]:
    profile = ctx.obj["profile"]
    return profile, ctx.obj["config"]


def _skills_dir(config: object, profile: str) -> Path:
    raw = getattr(config, "skills_dir", None)
    if raw:
        return Path(str(raw))
    return get_profile_manager().get_profile_dir(profile) / "data" / "skills"


def _save(profile: str, config: object) -> None:
    get_profile_manager().save_profile(profile, config)


@app.command("status")
def decision_status(ctx: typer.Context) -> None:
    """Show the decision preset, model, and optional skill. No secrets."""
    profile, config = _profile(ctx)
    raw = getattr(config, "decision", None) or {}
    resolved = resolve_decision(raw)
    skills_dir = _skills_dir(config, profile)
    installed = "on" if skill_installed(skills_dir, DECISION_SKILL) else "off"
    if resolved.preset == "jev":
        key = "set" if resolved.api_key else "missing"
    elif resolved.preset in {"nimble", "tev1"}:
        key = "not required"
    else:
        key = "set" if resolved.api_key else "missing"
    print_info(f"profile: {profile}")
    print_info(f"enabled: {'yes' if resolved.enabled else 'no'}")
    print_info(f"preset: {resolved.preset}")
    print_info(f"model: {resolved.model or '—'}")
    print_info(f"base_url: {resolved.base_url or '—'}")
    print_info(f"key: {key}")
    print_info(f"skill {DECISION_SKILL}: {installed}")
    internal = raw.get("internal") if isinstance(raw, dict) else {}
    internal = internal if isinstance(internal, dict) else {}
    flags = ", ".join(f"{name}={'on' if internal.get(name) else 'off'}" for name in INTERNAL_FLAGS)
    print_info(f"internal: {flags}")
    thresholds = raw.get("thresholds") if isinstance(raw, dict) else {}
    if isinstance(thresholds, dict) and thresholds:
        shown = ", ".join(
            f"{key}={thresholds[key]}"
            for key in ("noul", "confidence", "quality")
            if key in thresholds
        )
        print_info(f"thresholds: {shown}")


@app.command("use")
def decision_use(
    ctx: typer.Context,
    preset: str = typer.Argument(..., help="off, jev, nimble, tev1, or custom"),
    base_url: str | None = typer.Option(
        None, "--base-url", help="Endpoint origin, without /v1/systemone"
    ),
    model: str | None = typer.Option(
        None, "--model", help="Model id. jev defaults to multilingual jev-latest"
    ),
) -> None:
    """Select a decision preset. Existing profiles stay off until this runs."""
    profile, config = _profile(ctx)
    current = getattr(config, "decision", None) or {}
    try:
        block = configure_decision(current, preset, base_url=base_url, model=model)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    if block.get("preset") == "off":
        skills_dir = _skills_dir(config, profile)
        block = clear_skill(block, skills_dir, DECISION_SKILL)
    config.decision = block
    _save(profile, config)
    resolved = resolve_decision(block)
    print_success(f"Decision preset: {resolved.preset} ({'on' if resolved.enabled else 'off'})")
    if resolved.enabled:
        print_info(f"model: {resolved.model}")
        print_info(f"base_url: {resolved.base_url}")
    if resolved.preset == "jev" and not resolved.api_key:
        print_info(
            "Set DECISION_API_KEY in the profile .env. The key is not stored in config.yaml."
        )
    print_info("Restart the agent to register systemone_decide.")


@app.command("internal")
def decision_internal(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="on or off"),
    name: str = typer.Argument(..., help="reflexion, is_final, skill_choice, or shell_allow"),
) -> None:
    """Turn one internal gate on or off. The preset alone does not enable these."""
    verb = action.strip().lower()
    if verb not in {"on", "off"}:
        print_error("action must be on or off")
        raise typer.Exit(1)
    profile, config = _profile(ctx)
    try:
        block = set_internal_flag(getattr(config, "decision", None) or {}, name, verb == "on")
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    config.decision = block
    _save(profile, config)
    print_success(f"internal {name}: {verb}")


@app.command("threshold")
def decision_threshold(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="noul, confidence, or quality"),
    value: float = typer.Argument(..., help="From 0 to 1"),
) -> None:
    """Set the gate threshold. noul and confidence default to 0.8 and 0.6."""
    profile, config = _profile(ctx)
    try:
        block = set_threshold(getattr(config, "decision", None) or {}, name, value)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    config.decision = block
    _save(profile, config)
    print_success(f"threshold {name}: {block['thresholds'][name]}")


@app.command("probe")
def decision_probe(ctx: typer.Context) -> None:
    """Send one short noul. Prints ok or an error, not the request text."""
    _profile_name, config = _profile(ctx)
    resolved = resolve_decision(getattr(config, "decision", None) or {})
    text = asyncio.run(probe_decision(resolved))
    if text == "ok":
        print_success("ok")
        return
    print_error(text)
    raise typer.Exit(1)


@app.command("skills")
def decision_skills(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="on or off"),
    name: str = typer.Argument(DECISION_SKILL, help="Optional skill name"),
) -> None:
    """Copy or remove the optional decision skill. Requires the preset to be on."""
    verb = action.strip().lower()
    if verb not in {"on", "off"}:
        print_error("action must be on or off")
        raise typer.Exit(1)
    if name != DECISION_SKILL:
        print_error(f"This command only toggles {DECISION_SKILL}.")
        raise typer.Exit(1)
    profile, config = _profile(ctx)
    block = dict(getattr(config, "decision", None) or {})
    enabled = resolve_decision(block).enabled
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
    config.decision = updated
    _save(profile, config)
    print_success(f"{name}: {verb}")
