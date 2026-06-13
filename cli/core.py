"""Core profile management and initialization for Holix CLI."""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from core.platform_compat import resolve_holix_home
from core.profile_keys import (
    ProfileExistsError,
    ProfileNotFoundError,
    profile_has_access_key,
    require_profile_access_key,
    store_profile_access_key,
    verify_profile_access_key,
)
from pydantic import BaseModel, Field

# Holix home directory (HOLIX_HOME / XDG / %LOCALAPPDATA%\Holix / ~/.holix)
HOLIX_HOME = resolve_holix_home()
PROFILES_DIR = HOLIX_HOME / "profiles"
LOGS_DIR = HOLIX_HOME / "logs"


def profiles_dir() -> Path:
    """Resolve profiles root (honours HOLIX_HOME at call time for tests/runtime)."""
    home = os.environ.get("HOLIX_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve() / "profiles"
    return PROFILES_DIR


def logs_dir() -> Path:
    home = os.environ.get("HOLIX_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve() / "logs"
    return LOGS_DIR


class ProfileConfig(BaseModel):
    """Configuration for a Holix profile."""

    # LLM settings
    model: str = "qwen2.5-coder:32b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    temperature: float = 0.7
    max_steps: int = 15

    # Profile settings
    profile_name: str = "default"
    data_dir: str | None = None
    memory_db_path: str | None = None
    vector_db_path: str | None = None
    ltm_db_path: str | None = None
    langgraph_checkpoint_db_path: str | None = None
    skills_dir: str | None = None
    context_window: int | None = None  # None = use default (128k), otherwise token count

    # System prompt
    system_prompt: str | None = None

    # Model providers and routing
    providers: dict[str, Any] = Field(default_factory=dict)
    agent_models: dict[str, Any] = Field(default_factory=dict)
    default_provider: str | None = None
    fallback_providers: list[str] = Field(default_factory=list)
    models_via_providers: bool = False  # True after catalog providers were used

    # MCP (Model Context Protocol) servers — stored under ~/.holix only
    mcp_servers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    mcp_assignments: dict[str, list[str]] = Field(default_factory=dict)  # e.g. {"main": ["fs"], "researcher": ["fs", "git"]}
    mcp_enabled: bool = True

    # Skills: which skill names each agent/subagent may use (empty dict = all skills)
    skill_assignments: dict[str, list[str]] = Field(default_factory=dict)  # e.g. {"main": ["git"], "coder": ["git", "docker"]}

    # Sub-agents
    enable_subagents: bool | None = None
    subagent_default_process_mode: str | None = None
    subagent_max_concurrent: int | None = None

    # Hub: optional background ClawHub version updates
    hub_auto_update: bool = False
    hub_auto_update_interval_hours: float = 24.0

    # Web search providers (duckduckgo, searxng, firecrawl)
    search: dict[str, Any] = Field(default_factory=dict)

    # Workspace jail: restrict file/terminal tools to a single directory tree
    workspace_jail_enabled: bool = False
    workspace_root: str | None = None

    # At-rest encryption for workspace files (requires unlock key at runtime)
    encryption_enabled: bool = False


def _holix_env_name() -> str:
    return os.getenv("HOLIX_ENV", "development").strip().lower()


def default_profile_allowed() -> bool:
    """Implicit profile ``default`` is available only outside production."""
    return _holix_env_name() != "production"


_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


def validate_profile_name_for_env(profile: str) -> str:
    """Reject invalid, path-traversal, and reserved ``default`` profile names."""
    name = (profile or "").strip() or "default"

    if ".." in name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ProfileNotFoundError(f"Invalid profile name: {profile!r}")
    if not _PROFILE_NAME_RE.fullmatch(name):
        raise ProfileNotFoundError(f"Invalid profile name: {profile!r}")

    if _holix_env_name() == "production" and name == "default":
        raise ProfileNotFoundError(
            "Profile 'default' is only available when HOLIX_ENV is not production. "
            "Use a named profile: holix -p <name> …"
        )
    return name


def resolve_active_profile_name(explicit: str | None = None) -> str:
    """Resolve CLI/gateway profile from flag or dev-only implicit default."""
    if explicit and str(explicit).strip():
        return validate_profile_name_for_env(str(explicit).strip())
    if default_profile_allowed():
        return "default"
    raise ProfileNotFoundError(
        "Profile name is required when HOLIX_ENV=production. "
        "Example: holix -p alice gateway start"
    )


def enable_profile_workspace_isolation(
    manager: "ProfileManager",
    profile: str,
) -> Path:
    """Create per-profile workspace directory and enable jail."""
    from core.workspace.limits import ensure_profile_limits
    from core.workspace.quota import reconcile_workspace_usage

    profile_dir = manager.get_profile_dir(profile)
    workspace_dir = profile_dir / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    ensure_profile_limits(profile)
    reconcile_workspace_usage(workspace_dir)
    config = manager.load_profile(profile)
    config.workspace_jail_enabled = True
    config.workspace_root = str(workspace_dir.resolve())
    manager.save_profile(profile, config)
    return workspace_dir


def resolve_profile_storage_paths(
    profile: str,
    config: ProfileConfig,
    *,
    profile_dir: Path | None = None,
) -> ProfileConfig:
    """Bind profile storage paths to ~/.holix/profiles/<name>/ (not process CWD)."""
    base = (profile_dir or (profiles_dir() / profile)).resolve()

    def _path_is_writable(path: Path, *, mkdir_target: bool) -> bool:
        try:
            if mkdir_target:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".holix_write_probe"
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                probe = path.parent / ".holix_write_probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def _resolve(
        path: str | None,
        default: Path,
        *,
        mkdir_target: bool = False,
    ) -> str:
        """Resolve under profile dir; fall back when outside paths are not writable."""
        target = default.resolve()
        if path and str(path).strip():
            expanded = Path(path).expanduser()
            if expanded.is_absolute():
                candidate = expanded.resolve()
                try:
                    candidate.relative_to(base)
                    target = candidate
                except ValueError:
                    if _path_is_writable(candidate, mkdir_target=mkdir_target):
                        target = candidate
            else:
                target = (base / expanded).resolve()

        if not mkdir_target and target.exists() and target.is_dir():
            target = default.resolve()
        if not _path_is_writable(target, mkdir_target=mkdir_target):
            target = default.resolve()
            _path_is_writable(target, mkdir_target=mkdir_target)
        return str(target)

    config.profile_name = profile
    config.data_dir = _resolve(config.data_dir, base / "data", mkdir_target=True)
    config.memory_db_path = _resolve(
        config.memory_db_path,
        base / "data" / "memory" / "memory.db",
    )
    config.vector_db_path = _resolve(
        config.vector_db_path,
        base / "data" / "memory" / "vector_db",
        mkdir_target=True,
    )
    config.skills_dir = _resolve(
        config.skills_dir,
        base / "data" / "skills",
        mkdir_target=True,
    )
    # Keep all SQLite memory stores next to memory.db (fixes stale ltm/checkpoint paths).
    memory_dir = Path(config.memory_db_path).resolve().parent
    config.ltm_db_path = _resolve(
        str(memory_dir / "ltm.db"),
        memory_dir / "ltm.db",
    )
    config.langgraph_checkpoint_db_path = _resolve(
        str(memory_dir / "checkpoints.db"),
        memory_dir / "checkpoints.db",
    )
    if config.workspace_root and str(config.workspace_root).strip():
        config.workspace_root = _resolve(config.workspace_root, base / "workspace")
    else:
        config.workspace_root = None
    return config


class ProfileManager:
    """Manage Holix profiles."""

    def __init__(self):
        """Initialize profile manager."""
        self._last_created_access_key: str | None = None
        self.ensure_directories()

    def ensure_directories(self):
        """Ensure Holix directories exist."""
        from core.env_loader import init_holix_home

        init_holix_home()
        profiles_dir().mkdir(parents=True, exist_ok=True)
        logs_dir().mkdir(parents=True, exist_ok=True)

    def get_profile_dir(self, profile: str) -> Path:
        """Get profile directory path.

        Args:
            profile: Profile name

        Returns:
            Path to profile directory
        """
        return profiles_dir() / profile

    def profile_exists(self, profile: str) -> bool:
        """Check if profile exists.

        Args:
            profile: Profile name

        Returns:
            True if profile exists
        """
        config_file = self.get_profile_dir(profile) / "config.yaml"
        return config_file.exists()

    def create_profile(
        self,
        profile: str,
        config: ProfileConfig | None = None,
        *,
        with_access_key: bool = False,
        inherit_global: bool = True,
    ) -> ProfileConfig:
        """Create a new profile.

        Args:
            profile: Profile name
            config: Optional profile configuration
            with_access_key: Generate a profile access key on creation (opt-in)
            inherit_global: When True, profile inherits ``global/`` settings and
                stores only overrides. When False (--clean), write a standalone config.

        Returns:
            Profile configuration
        """
        if self.profile_exists(profile):
            raise ProfileExistsError(f"Profile '{profile}' already exists")
        profile_dir = self.get_profile_dir(profile)
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (profile_dir / "data" / "memory").mkdir(parents=True, exist_ok=True)
        skills_path = profile_dir / "data" / "skills"
        skills_path.mkdir(parents=True, exist_ok=True)
        seeded: list[str] = []
        try:
            from core.skills.bundled import seed_bundled_skills

            seeded = seed_bundled_skills(skills_path)
        except Exception:
            pass
        (profile_dir / "data" / "security").mkdir(parents=True, exist_ok=True)
        (profile_dir / "data" / "files").mkdir(parents=True, exist_ok=True)
        (profile_dir / "gateway").mkdir(parents=True, exist_ok=True)

        from core.env_loader import ensure_profile_env_template
        from core.profile.soul import bootstrap_profile_identity

        ensure_profile_env_template(profile, inherit_global=inherit_global)
        bootstrap_profile_identity(profile)

        from core.workspace.limits import ensure_profile_limits

        ensure_profile_limits(profile)

        # Set default config if not provided
        if config is None:
            config = ProfileConfig(profile_name=profile)
        else:
            config.profile_name = profile

        config = resolve_profile_storage_paths(profile, config, profile_dir=profile_dir)
        storage_mode = "sparse" if inherit_global else "full"

        if with_access_key:
            workspace_dir = profile_dir / "workspace"
            workspace_dir.mkdir(parents=True, exist_ok=True)
            config.workspace_jail_enabled = True
            config.workspace_root = str(workspace_dir.resolve())

        if seeded:
            try:
                from core.skills.bundled import ensure_bundled_assigned_to_main

                assigns, _ = ensure_bundled_assigned_to_main(
                    getattr(config, "skill_assignments", None) or {},
                    seeded,
                )
                config.skill_assignments = assigns
            except Exception:
                pass

        # Save config (inherit mode: only profile_name + per-profile paths, no model defaults)
        if storage_mode == "sparse" and inherit_global:
            from core.global_config import PROFILE_ONLY_KEYS

            storage: dict[str, Any] = {"profile_name": profile}
            for key in PROFILE_ONLY_KEYS:
                if key == "profile_name":
                    continue
                value = getattr(config, key, None)
                if value is not None and value is not False and value != "":
                    storage[key] = value
            self._write_profile_yaml(profile, storage)
        else:
            self.save_profile(profile, config, storage_mode=storage_mode)

        self._last_created_access_key = None
        if with_access_key and not profile_has_access_key(profile):
            self._last_created_access_key = store_profile_access_key(profile)

        return config

    def pop_last_created_access_key(self) -> str | None:
        """Return access key from the most recent create_profile() call."""
        key = self._last_created_access_key
        self._last_created_access_key = None
        return key

    def load_profile(self, profile: str) -> ProfileConfig:
        """Load profile configuration.

        Args:
            profile: Profile name

        Returns:
            Profile configuration
        """
        if not self.profile_exists(profile):
            if profile == "default" and default_profile_allowed():
                return self.create_profile(profile)
            raise ProfileNotFoundError(f"Profile '{profile}' does not exist")

        config_file = self.get_profile_dir(profile) / "config.yaml"

        with open(config_file, encoding="utf-8") as f:
            profile_data = yaml.safe_load(f) or {}

        from core.config_utils import load_local_overlay, merge_profile_with_local, resolve_env_refs
        from core.global_config import load_global_config_resolved, merge_global_with_profile

        global_data = load_global_config_resolved()
        data = merge_global_with_profile(global_data, profile_data)
        data = resolve_env_refs(data)
        from core.models.profile_cleanup import sanitize_model_routing_data

        data = sanitize_model_routing_data(data)
        # Supplement with project-local .holix/config.yaml (additive only: mcp, not models/system)
        local = load_local_overlay()
        data = merge_profile_with_local(data, local)
        config = ProfileConfig(**data)
        return resolve_profile_storage_paths(profile, config, profile_dir=self.get_profile_dir(profile))

    def _write_profile_yaml(self, profile: str, data: dict[str, Any]) -> None:
        config_file = self.get_profile_dir(profile) / "config.yaml"
        with open(config_file, "w", encoding="utf-8") as handle:
            yaml.dump(data, handle, default_flow_style=False, allow_unicode=True)

    def save_profile(
        self,
        profile: str,
        config: ProfileConfig,
        *,
        storage_mode: str = "sparse",
    ):
        """Save profile configuration.

        Args:
            profile: Profile name
            config: Profile configuration
            storage_mode: ``sparse`` stores only overrides vs global; ``full`` writes all fields
        """
        from core.global_config import extract_profile_overrides, load_global_config_resolved

        payload = config.model_dump()
        if storage_mode == "full":
            storage = payload
        else:
            storage = extract_profile_overrides(payload, load_global_config_resolved())
        self._write_profile_yaml(profile, storage)

    def list_profiles(self) -> list[str]:
        """List all available profiles.

        Returns:
            List of profile names
        """
        root = profiles_dir()
        if not root.exists():
            return []

        profiles = []
        for item in root.iterdir():
            if item.is_dir() and (item / "config.yaml").exists():
                profiles.append(item.name)

        return sorted(profiles)

    def delete_profile(self, profile: str) -> bool:
        """Delete a profile.

        Args:
            profile: Profile name

        Returns:
            True if deleted successfully
        """
        if profile == "default":
            return False  # Don't delete default profile

        profile_dir = self.get_profile_dir(profile)
        if profile_dir.exists():
            import shutil
            shutil.rmtree(profile_dir)
            return True

        return False


# Global profile manager
_profile_manager = ProfileManager()
_current_profile: str | None = None
_current_config: ProfileConfig | None = None
_unlocked_profiles: set[str] = set()


def _resolve_profile_key(profile_key: str | None) -> str | None:
    if profile_key and str(profile_key).strip():
        return str(profile_key).strip()
    env_key = os.getenv("HOLIX_PROFILE_KEY", "").strip()
    return env_key or None


def _ensure_profile_unlocked(
    profile: str,
    *,
    profile_key: str | None = None,
    prompt_key: bool = True,
) -> None:
    if profile in _unlocked_profiles:
        return
    key = _resolve_profile_key(profile_key)
    if not key and prompt_key:
        try:
            import sys

            import typer

            if sys.stdin.isatty() and profile_has_access_key(profile):
                key = typer.prompt(
                    f"Access key for profile '{profile}'",
                    hide_input=True,
                )
        except Exception:
            pass
    require_profile_access_key(profile, key)
    _unlocked_profiles.add(profile)


def unlock_profile(profile: str, profile_key: str) -> bool:
    """Verify and remember a profile access key for this process."""
    if not verify_profile_access_key(profile, profile_key):
        return False
    _unlocked_profiles.add(profile)
    return True


def unlock_profile_encryption(profile: str, unlock_key: str) -> None:
    """Derive DEK from user encryption key and cache it for this process."""
    from core.crypto.profile_crypto import unlock_profile_dek
    from core.crypto.unlock_context import set_profile_session_unlock

    dek = unlock_profile_dek(profile, unlock_key)
    set_profile_session_unlock(profile, dek)


def bootstrap_profile_unlock_from_env(profile: str) -> bool:
    """Unlock encrypted profile using HOLIX_UNLOCK_KEY from the environment."""
    from core.crypto.unlock_context import bootstrap_profile_unlock_from_env as _bootstrap

    return _bootstrap(profile)


def init_profile(
    profile: str | None = None,
    *,
    profile_key: str | None = None,
    unlock_key: str | None = None,
    prompt_key: bool = True,
) -> ProfileConfig:
    """Initialize a profile for CLI session.

    Args:
        profile: Profile name
        profile_key: Optional access key for protected profiles
        prompt_key: Prompt interactively when key is required

    Returns:
        Profile configuration
    """
    global _current_profile, _current_config

    from core.env_loader import bootstrap_profile_env

    profile = resolve_active_profile_name(profile)
    _ensure_profile_unlocked(profile, profile_key=profile_key, prompt_key=prompt_key)

    switching = _current_profile is not None and _current_profile != profile
    bootstrap_profile_env(profile, force=switching or _current_profile is None)
    _current_profile = profile
    _current_config = _profile_manager.load_profile(profile)

    if unlock_key and unlock_key.strip():
        from core.crypto.profile_crypto import is_profile_encryption_enabled

        key = unlock_key.strip()
        os.environ["HOLIX_UNLOCK_KEY"] = key
        if is_profile_encryption_enabled(profile) or getattr(_current_config, "encryption_enabled", False):
            unlock_profile_encryption(profile, key)

    created_key = _profile_manager.pop_last_created_access_key()
    if created_key:
        try:
            from cli.utils.rich_console import print_panel

            print_panel(
                f"[cyan]{created_key}[/cyan]\n\n"
                f"Save this access key for profile '{profile}' — it is shown only once.\n"
                f"Use: [bold]holix -p {profile} --profile-key <key>[/bold]",
                title="Profile access key",
                border_style="yellow",
            )
        except Exception:
            pass

    return _current_config


def get_current_profile() -> str:
    """Get current profile name.

    Returns:
        Current profile name
    """
    global _current_profile
    if _current_profile:
        return _current_profile
    return resolve_active_profile_name(None)


def get_current_config() -> ProfileConfig:
    """Get current profile configuration.

    Returns:
        Current profile configuration
    """
    global _current_config

    if _current_config is None:
        _current_config = init_profile()

    return _current_config


def switch_profile(profile: str, *, profile_key: str | None = None) -> ProfileConfig:
    """Switch to a different profile.

    Args:
        profile: Profile name
        profile_key: Optional access key for protected profiles

    Returns:
        New profile configuration
    """
    return init_profile(profile, profile_key=profile_key)


def get_profile_manager() -> ProfileManager:
    """Get the global profile manager.

    Returns:
        Profile manager instance
    """
    return _profile_manager
