"""Shared configuration helpers."""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_REF = re.compile(r"^\$\{([A-Z0-9_]+)(?::([^}]*))?\}$")
_INLINE_ENV_REF = re.compile(r"\$\{([A-Z0-9_]+)(?::([^}]*))?\}")


def substitute_env_in_string(text: str, *, leave_missing: bool = True) -> str:
    """Replace inline ${VAR} / ${ENV:VAR} with os.environ values."""
    if not text or "${" not in text:
        return text

    def _repl(match: re.Match[str]) -> str:
        var = match.group(2) or match.group(1)
        if var in os.environ:
            return os.environ[var]
        return match.group(0) if leave_missing else ""

    return _INLINE_ENV_REF.sub(_repl, text)


def is_subagents_enabled(cfg: Any, *, default: bool = True) -> bool:
    """Return whether sub-agents are enabled (default on when unset)."""
    if cfg is None:
        return default
    value = getattr(cfg, "enable_subagents", None)
    if value is None:
        return default
    return bool(value)


def resolve_env_refs(value: Any) -> Any:
    """Resolve ${VAR} and ${ENV:VAR} placeholders in YAML-loaded values."""
    if isinstance(value, str):
        stripped = value.strip()
        m = _ENV_REF.match(stripped)
        if m:
            var = m.group(2) or m.group(1)
            return os.environ.get(var, "")
        return substitute_env_in_string(value)
    if isinstance(value, dict):
        return {k: resolve_env_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_refs(v) for v in value]
    return value


# --- Project-local .holix/ supplement support (skills, plans, extra mcp; NO system/model keys) ---

from pathlib import Path

_LOCAL_SYSTEM_KEYS: frozenset[str] = frozenset({
    "model", "base_url", "api_key", "temperature", "max_steps",
    "providers", "agent_models", "default_provider",
    "auto_allow_threshold", "non_interactive", "confirmation_timeout",
    "plan_review_enabled", "plan_review_timeout",
    "enable_subagents", "enable_meta_agent", "enable_self_refinement",
    "enable_evolution", "context_window",
    # security-ish that must stay global
    "api_key_pepper", "require_auth",
})


def get_local_holix_dir(cwd: str | None = None) -> Path:
    """Return <cwd>/.holix (or CWD/.holix). Falls back to legacy .helix when present."""
    base = Path(cwd) if cwd else Path.cwd()
    holix = base / ".holix"
    helix = base / ".helix"
    if helix.is_dir() and not holix.is_dir():
        return helix
    return holix


def load_local_overlay(cwd: str | None = None) -> dict[str, Any]:
    """Load .holix/config.yaml if present (for supplements only). Returns {} if absent."""
    local_dir = get_local_holix_dir(cwd)
    cfg_file = local_dir / "config.yaml"
    if not cfg_file.exists():
        return {}
    try:
        import yaml  # lazy
        with open(cfg_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return resolve_env_refs(data)
    except Exception as exc:
        print(f"Warning: failed to load local .holix/config.yaml: {exc}")
        return {}


def merge_profile_with_local(profile_data: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    """Merge only additive/safe keys from local overlay into profile data.

    System/model keys from local are ignored (never override ~/.holix profile).
    """
    if not local:
        return profile_data

    merged = dict(profile_data)  # shallow ok for our use
    # mcp_servers: additive merge (local can add/override specific servers)
    if "mcp_servers" in local and isinstance(local["mcp_servers"], dict):
        base_mcp = merged.get("mcp_servers") or {}
        merged["mcp_servers"] = {**base_mcp, **local["mcp_servers"]}

    # mcp_assignments: additive per-agent
    if "mcp_assignments" in local and isinstance(local["mcp_assignments"], dict):
        base_assign = merged.get("mcp_assignments") or {}
        merged["mcp_assignments"] = {**base_assign, **local["mcp_assignments"]}

    if "skill_assignments" in local and isinstance(local["skill_assignments"], dict):
        base_sk = merged.get("skill_assignments") or {}
        merged["skill_assignments"] = {**base_sk, **local["skill_assignments"]}

    # local mcp toggle (rare)
    if "mcp_enabled" in local:
        merged["mcp_enabled"] = bool(local["mcp_enabled"])

    # For skills etc we handle in the managers (paths), not here.
    # Explicitly drop any system keys that might have been in local
    for k in _LOCAL_SYSTEM_KEYS:
        if k in merged and k in local:
            # keep the profile one; drop/ignore local
            pass  # already from profile_data

    return merged


def get_local_skills_dir(cwd: str | None = None) -> Path | None:
    d = get_local_holix_dir(cwd) / "skills"
    return d if d.exists() else None


def get_local_plan_dir(cwd: str | None = None) -> Path:
    return get_local_holix_dir(cwd) / "plans"