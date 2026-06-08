"""Core profile management and initialization for Helix CLI."""

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.platform_compat import resolve_helix_home

# Helix home directory (HELIX_HOME / XDG / %LOCALAPPDATA%\Helix / ~/.helix)
HELIX_HOME = resolve_helix_home()
PROFILES_DIR = HELIX_HOME / "profiles"
LOGS_DIR = HELIX_HOME / "logs"


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
    data_dir: Optional[str] = None
    memory_db_path: Optional[str] = None
    vector_db_path: Optional[str] = None
    ltm_db_path: Optional[str] = None
    langgraph_checkpoint_db_path: Optional[str] = None
    skills_dir: Optional[str] = None
    context_window: Optional[int] = None  # None = use default (128k), otherwise token count

    # System prompt
    system_prompt: Optional[str] = None

    # Model providers and routing
    providers: Dict[str, Any] = Field(default_factory=dict)
    agent_models: Dict[str, Any] = Field(default_factory=dict)
    default_provider: Optional[str] = None
    models_via_providers: bool = False  # True after catalog providers were used

    # MCP (Model Context Protocol) servers — stored under ~/.helix only
    mcp_servers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    mcp_assignments: Dict[str, List[str]] = Field(default_factory=dict)  # e.g. {"main": ["fs"], "researcher": ["fs", "git"]}
    mcp_enabled: bool = True

    # Skills: which skill names each agent/subagent may use (empty dict = all skills)
    skill_assignments: Dict[str, List[str]] = Field(default_factory=dict)  # e.g. {"main": ["git"], "coder": ["git", "docker"]}

    # Sub-agents
    enable_subagents: Optional[bool] = None
    subagent_default_process_mode: Optional[str] = None
    subagent_max_concurrent: Optional[int] = None

    # Hub: optional background ClawHub version updates
    hub_auto_update: bool = False
    hub_auto_update_interval_hours: float = 24.0

    # Web search providers (duckduckgo, searxng, firecrawl)
    search: Dict[str, Any] = Field(default_factory=dict)

    # Workspace jail: restrict file/terminal tools to a single directory tree
    workspace_jail_enabled: bool = False
    workspace_root: Optional[str] = None


def resolve_profile_storage_paths(
    profile: str,
    config: ProfileConfig,
    *,
    profile_dir: Path | None = None,
) -> ProfileConfig:
    """Bind profile storage paths to ~/.helix/profiles/<name>/ (not process CWD)."""
    base = (profile_dir or (PROFILES_DIR / profile)).resolve()

    def _resolve(path: Optional[str], default: Path) -> str:
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
        self.ensure_directories()

    def ensure_directories(self):
        """Ensure Helix directories exist."""
        from core.env_loader import init_helix_home

        init_helix_home()
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def get_profile_dir(self, profile: str) -> Path:
        """Get profile directory path.

        Args:
            profile: Profile name

        Returns:
            Path to profile directory
        """
        return PROFILES_DIR / profile

    def profile_exists(self, profile: str) -> bool:
        """Check if profile exists.

        Args:
            profile: Profile name

        Returns:
            True if profile exists
        """
        config_file = self.get_profile_dir(profile) / "config.yaml"
        return config_file.exists()

    def create_profile(self, profile: str, config: Optional[ProfileConfig] = None) -> ProfileConfig:
        """Create a new profile.

        Args:
            profile: Profile name
            config: Optional profile configuration

        Returns:
            Profile configuration
        """
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

        return config

    def load_profile(self, profile: str) -> ProfileConfig:
        """Load profile configuration.

        Args:
            profile: Profile name

        Returns:
            Profile configuration
        """
        if not self.profile_exists(profile):
            # Create default profile
            return self.create_profile(profile)

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
        if not PROFILES_DIR.exists():
            return []

        profiles = []
        for item in PROFILES_DIR.iterdir():
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
_current_profile: Optional[str] = None
_current_config: Optional[ProfileConfig] = None


def init_profile(profile: str = "default") -> ProfileConfig:
    """Initialize a profile for CLI session.

    Args:
        profile: Profile name

    Returns:
        Profile configuration
    """
    global _current_profile, _current_config

    from core.env_loader import bootstrap_profile_env

    switching = _current_profile is not None and _current_profile != profile
    bootstrap_profile_env(profile, force=switching or _current_profile is None)
    _current_profile = profile
    _current_config = _profile_manager.load_profile(profile)

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


def switch_profile(profile: str) -> ProfileConfig:
    """Switch to a different profile.

    Args:
        profile: Profile name

    Returns:
        New profile configuration
    """
    return init_profile(profile)


def get_profile_manager() -> ProfileManager:
    """Get the global profile manager.

    Returns:
        Profile manager instance
    """
    return _profile_manager
