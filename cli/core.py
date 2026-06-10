"""Core profile management and initialization for Helix CLI."""

import os
from pathlib import Path
from typing import Any

import yaml
from core.platform_compat import resolve_helix_home
from core.profile_keys import (
    ProfileExistsError,
    ProfileNotFoundError,
    profile_has_access_key,
    require_profile_access_key,
    store_profile_access_key,
    verify_profile_access_key,
)
from pydantic import BaseModel, Field

# Helix home directory (HELIX_HOME / XDG / %LOCALAPPDATA%\Helix / ~/.helix)
HELIX_HOME = resolve_helix_home()
PROFILES_DIR = HELIX_HOME / "profiles"
LOGS_DIR = HELIX_HOME / "logs"


def profiles_dir() -> Path:
    """Resolve profiles root (honours HELIX_HOME at call time for tests/runtime)."""
    home = os.environ.get("HELIX_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve() / "profiles"
    return PROFILES_DIR


def logs_dir() -> Path:
    home = os.environ.get("HELIX_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve() / "logs"
    return LOGS_DIR


class ProfileConfig(BaseModel):
    """Configuration for a Helix profile."""

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
    models_via_providers: bool = False  # True after catalog providers were used

    # MCP (Model Context Protocol) servers — stored under ~/.helix only
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


def resolve_profile_storage_paths(
    profile: str,
    config: ProfileConfig,
    *,
    profile_dir: Path | None = None,
) -> ProfileConfig:
    """Bind profile storage paths to ~/.helix/profiles/<name>/ (not process CWD)."""
    base = (profile_dir or (profiles_dir() / profile)).resolve()

    def _resolve(path: str | None, default: Path) -> str:
        if not path or not str(path).strip():
            return str(default.resolve())
        expanded = Path(path).expanduser()
        if expanded.is_absolute():
            return str(expanded.resolve())
        return str((base / expanded).resolve())

    config.profile_name = profile
    config.data_dir = _resolve(config.data_dir, base / "data")
    config.memory_db_path = _resolve(
        config.memory_db_path,
        base / "data" / "memory" / "memory.db",
    )
    config.vector_db_path = _resolve(
        config.vector_db_path,
        base / "data" / "memory" / "vector_db",
    )
    config.ltm_db_path = _resolve(
        config.ltm_db_path,
        base / "data" / "memory" / "ltm.db",
    )
    config.langgraph_checkpoint_db_path = _resolve(
        config.langgraph_checkpoint_db_path,
        base / "data" / "memory" / "checkpoints.db",
    )
    config.skills_dir = _resolve(config.skills_dir, base / "data" / "skills")
    if config.workspace_root and str(config.workspace_root).strip():
        config.workspace_root = _resolve(config.workspace_root, base / "workspace")
    else:
        config.workspace_root = None
    return config


class ProfileManager:
    """Manage Helix profiles."""

    def __init__(self):
        """Initialize profile manager."""
        self._last_created_access_key: str | None = None
        self.ensure_directories()

    def ensure_directories(self):
        """Ensure Helix directories exist."""
        from core.env_loader import init_helix_home

        init_helix_home()
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
    ) -> ProfileConfig:
        """Create a new profile.

        Args:
            profile: Profile name
            config: Optional profile configuration
            with_access_key: Generate a profile access key on creation (opt-in)

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

        ensure_profile_env_template(profile)

        # Set default config if not provided
        if config is None:
            config = ProfileConfig(profile_name=profile)
        else:
            config.profile_name = profile

        config = resolve_profile_storage_paths(profile, config, profile_dir=profile_dir)

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

        # Save config
        self.save_profile(profile, config)

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
            if profile == "default":
                return self.create_profile(profile)
            raise ProfileNotFoundError(f"Profile '{profile}' does not exist")

        config_file = self.get_profile_dir(profile) / "config.yaml"

        with open(config_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        from core.config_utils import load_local_overlay, merge_profile_with_local, resolve_env_refs

        data = resolve_env_refs(data)
        from core.models.profile_cleanup import sanitize_model_routing_data

        data = sanitize_model_routing_data(data)
        # Supplement with project-local .helix/config.yaml (additive only: mcp, not models/system)
        local = load_local_overlay()
        data = merge_profile_with_local(data, local)
        config = ProfileConfig(**data)
        return resolve_profile_storage_paths(profile, config, profile_dir=self.get_profile_dir(profile))

    def save_profile(self, profile: str, config: ProfileConfig):
        """Save profile configuration.

        Args:
            profile: Profile name
            config: Profile configuration
        """
        config_file = self.get_profile_dir(profile) / "config.yaml"

        with open(config_file, 'w') as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False)

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
    env_key = os.getenv("HELIX_PROFILE_KEY", "").strip()
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


def init_profile(
    profile: str = "default",
    *,
    profile_key: str | None = None,
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

    _ensure_profile_unlocked(profile, profile_key=profile_key, prompt_key=prompt_key)

    switching = _current_profile is not None and _current_profile != profile
    bootstrap_profile_env(profile, force=switching or _current_profile is None)
    _current_profile = profile
    _current_config = _profile_manager.load_profile(profile)
    created_key = _profile_manager.pop_last_created_access_key()
    if created_key:
        try:
            from cli.utils.rich_console import print_panel

            print_panel(
                f"[cyan]{created_key}[/cyan]\n\n"
                f"Save this access key for profile '{profile}' — it is shown only once.\n"
                f"Use: [bold]helix -p {profile} --profile-key <key>[/bold]",
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
    return _current_profile or "default"


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
