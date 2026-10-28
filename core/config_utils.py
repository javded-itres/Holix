"""Shared configuration helpers."""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_REF = re.compile(r"^\$\{([A-Z0-9_]{1,64})(?::([^}\n]{0,512}))?\}$")
_INLINE_ENV_REF = re.compile(r"\$\{([A-Z0-9_]{1,64})(?::([^}\n]{0,512}))?\}")
_MAX_ENV_SUB_BYTES = 256_000


def substitute_env_in_string(text: str, *, leave_missing: bool = True) -> str:
    """Replace inline ${VAR} / ${ENV:VAR} with os.environ values."""
    if not text or "${" not in text:
        return text
    if len(text.encode("utf-8", errors="replace")) > _MAX_ENV_SUB_BYTES:
        return text

    def _repl(match: re.Match[str]) -> str:
        var = match.group(2) or match.group(1)
        if var in os.environ:
            return os.environ[var]
        return match.group(0) if leave_missing else ""

    return _INLINE_ENV_REF.sub(_repl, text)


def is_meta_agent_enabled(cfg: Any, *, default: bool = True) -> bool:
    """Whether the meta-agent advisory node should run."""
    if cfg is None:
        return default
    value = getattr(cfg, "enable_meta_agent", None)
    if value is None:
        return default
    return bool(value)


def is_self_refinement_enabled(cfg: Any, *, default: bool = False) -> bool:
    """Whether Reflexion / self-refinement after draft answers is enabled.

    Default is off when unset (messenger-safe).
    """
    if cfg is None:
        return default
    value = getattr(cfg, "enable_self_refinement", None)
    if value is None:
        return default
    return bool(value)


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

_LOCAL_SYSTEM_KEYS: frozenset[str] = frozenset(
    {
        "model",
        "base_url",
        "api_key",
        "temperature",
        "max_steps",
        "max_steps_extend_enabled",
        "max_steps_extend_by",
        "max_steps_max_extensions",
        "max_steps_user_max_extensions",
        "max_steps_hard_cap",
        "subagent_supervisor_enabled",
        "git_worktrees_enabled",
        "subagent_supervisor_poll_s",
        "subagent_supervisor_idle_s",
        "subagent_supervisor_max_interventions",
        "subagent_supervisor_cooldown_s",
        "subagent_supervisor_loop_cooldown_s",
        "providers",
        "agent_models",
        "default_provider",
        "auto_allow_threshold",
        "non_interactive",
        "confirmation_timeout",
        "plan_review_enabled",
        "plan_review_timeout",
        "enable_subagents",
        "enable_meta_agent",
        "enable_self_refinement",
        "agent_pipeline",
        "enable_evolution",
        "context_window",
        # security-ish that must stay global
        "api_key_pepper",
        "require_auth",
    }
)


def get_local_holix_dir(cwd: str | None = None) -> Path:
    """Return <cwd>/.holix (or CWD/.holix)."""
    base = Path(cwd) if cwd else Path.cwd()
    return base / ".holix"


def project_holix_dir(*, workspace_root: str | Path | None = None) -> Path:
    """`.holix` inside the agent workspace.

    A live session workspace wins. Otherwise use the profile workspace root.
    The process working directory is only the fallback when neither is set.
    Skills and MCP in this directory add to the profile and override the same name.
    """
    try:
        from core.workspace import get_configured_workspace_root

        session_root = get_configured_workspace_root()
    except Exception:
        session_root = None
    if session_root is not None:
        return session_root / ".holix"
    raw = str(workspace_root or "").strip()
    if raw:
        return Path(raw).expanduser() / ".holix"
    return Path.cwd() / ".holix"


def load_local_overlay(
    cwd: str | None = None,
    *,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load workspace `.holix/config.yaml` (skills/MCP supplement). {} if absent.

    ``cwd`` is the legacy explicit directory (tests and callers that already
    know the project root). Otherwise the file is read from
    :func:`project_holix_dir`.
    """
    if cwd is not None:
        local_dir = get_local_holix_dir(cwd)
    else:
        local_dir = project_holix_dir(workspace_root=workspace_root)
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
    # mcp_servers: local names are added and replace the profile entry of the same name
    local_servers = local.get("mcp_servers") if isinstance(local.get("mcp_servers"), dict) else {}
    if local_servers:
        base_mcp = dict(merged.get("mcp_servers") or {})
        base_mcp.update(local_servers)
        merged["mcp_servers"] = base_mcp
        assigns = dict(merged.get("mcp_assignments") or {})
        if "main" in assigns:
            names = [str(item) for item in (assigns.get("main") or []) if str(item).strip()]
            for key in local_servers:
                if str(key) not in names:
                    names.append(str(key))
            assigns["main"] = names
            merged["mcp_assignments"] = assigns

    # mcp_assignments: a slot listed locally replaces that slot's profile list
    if "mcp_assignments" in local and isinstance(local["mcp_assignments"], dict):
        base_assign = dict(merged.get("mcp_assignments") or {})
        base_assign.update(local["mcp_assignments"])
        merged["mcp_assignments"] = base_assign

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


def get_local_skills_dir(
    cwd: str | None = None,
    *,
    workspace_root: str | Path | None = None,
) -> Path | None:
    """Workspace `.holix/skills` when that directory exists."""
    if cwd is not None:
        d = get_local_holix_dir(cwd) / "skills"
    else:
        d = project_holix_dir(workspace_root=workspace_root) / "skills"
    return d if d.is_dir() else None


def get_local_plan_dir(cwd: str | None = None) -> Path:
    return get_local_holix_dir(cwd) / "plans"
