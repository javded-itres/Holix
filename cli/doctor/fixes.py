"""Deterministic doctor fixes (safe, no LLM)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import yaml

from cli.core import ProfileConfig, ProfileManager
from cli.doctor.findings import DoctorFinding
from cli.services.gateway_state import clear_state


def apply_deterministic_fixes(profile: str, findings: list[DoctorFinding]) -> list[str]:
    """Apply fixes for findings with fix_id. Returns human-readable actions taken."""
    applied: list[str] = []
    fix_ids = {f.fix_id for f in findings if f.fix_id}
    manager = ProfileManager()

    handlers: dict[str, Callable[[str, ProfileManager, DoctorFinding], str | None]] = {
        "create_profile": _fix_create_profile,
        "ensure_dirs": _fix_ensure_dirs,
        "init_paths": _fix_init_paths,
        "clear_gateway_state": _fix_clear_gateway_state,
        "fix_default_provider": _fix_default_provider,
        "fix_model_from_list": _fix_model_from_list,
    }

    for finding in findings:
        if not finding.fix_id or finding.fix_id not in fix_ids:
            continue
        handler = handlers.get(finding.fix_id)
        if handler is None:
            continue
        msg = handler(profile, manager, finding)
        if msg:
            applied.append(msg)
            fix_ids.discard(finding.fix_id)

    return applied


def _fix_create_profile(profile: str, manager: ProfileManager, _f: DoctorFinding) -> str:
    manager.create_profile(profile)
    return f"Created profile '{profile}' with default layout"


def _fix_ensure_dirs(profile: str, manager: ProfileManager, finding: DoctorFinding) -> str:
    cfg = manager.load_profile(profile)
    dirs = finding.context.get("dirs") or []
    if not dirs:
        profile_dir = manager.get_profile_dir(profile)
        for rel in (
            profile_dir / "data" / "memory",
            profile_dir / "data" / "skills",
            profile_dir / "data" / "security",
            Path(cfg.vector_db_path) if cfg.vector_db_path else profile_dir / "data" / "memory" / "vector_db",
        ):
            rel.mkdir(parents=True, exist_ok=True)
    else:
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)
    return "Created missing profile directories"


def _fix_init_paths(profile: str, manager: ProfileManager, _f: DoctorFinding) -> str:
    profile_dir = manager.get_profile_dir(profile)
    cfg = manager.load_profile(profile)
    cfg.data_dir = str(profile_dir / "data")
    cfg.memory_db_path = str(profile_dir / "data" / "memory" / "memory.db")
    cfg.vector_db_path = str(profile_dir / "data" / "memory" / "vector_db")
    cfg.skills_dir = str(profile_dir / "data" / "skills")
    manager.save_profile(profile, cfg)
    _fix_ensure_dirs(profile, manager, _f)
    return "Set standard profile paths in config.yaml"


def _fix_clear_gateway_state(_profile: str, _manager: ProfileManager, _f: DoctorFinding) -> str:
    clear_state()
    return "Removed stale gateway state file"


def _fix_default_provider(profile: str, manager: ProfileManager, finding: DoctorFinding) -> str:
    cfg = manager.load_profile(profile)
    available: list[str] = finding.context.get("available") or list(cfg.providers.keys())
    if not available:
        cfg.default_provider = None
        manager.save_profile(profile, cfg)
        return "Cleared invalid default_provider (no providers defined)"
    cfg.default_provider = available[0]
    manager.save_profile(profile, cfg)
    return f"Set default_provider to '{available[0]}'"


def _fix_model_from_list(profile: str, manager: ProfileManager, finding: DoctorFinding) -> str:
    cfg = manager.load_profile(profile)
    available: list[str] = finding.context.get("available") or []
    if not available:
        return ""
    new_model = available[0]
    base_url = finding.context.get("base_url", "")
    api_key = finding.context.get("api_key", "dummy")

    if cfg.default_provider and cfg.providers:
        pname = cfg.default_provider
        if pname in cfg.providers:
            cfg.providers[pname]["default_model"] = new_model
            if base_url:
                cfg.providers[pname]["base_url"] = base_url
            if api_key:
                cfg.providers[pname]["api_key"] = api_key
    else:
        cfg.model = new_model
        if base_url:
            cfg.base_url = base_url
        if api_key:
            cfg.api_key = api_key

    manager.save_profile(profile, cfg)
    return f"Set default model to '{new_model}'"


def backup_config(path: Path) -> Path:
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    return backup