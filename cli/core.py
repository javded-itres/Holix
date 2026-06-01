"""Core profile management and initialization for Helix CLI."""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

# Helix home directory
HELIX_HOME = Path.home() / ".helix"
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
    skills_dir: Optional[str] = None

    # System prompt
    system_prompt: Optional[str] = None

    # Model providers and routing
    providers: Dict[str, Any] = Field(default_factory=dict)
    agent_models: Dict[str, Any] = Field(default_factory=dict)
    default_provider: Optional[str] = None


class ProfileManager:
    """Manage Helix profiles."""

    def __init__(self):
        """Initialize profile manager."""
        self.ensure_directories()

    def ensure_directories(self):
        """Ensure Helix directories exist."""
        HELIX_HOME.mkdir(parents=True, exist_ok=True)
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
        (profile_dir / "data" / "skills").mkdir(parents=True, exist_ok=True)
        (profile_dir / "data" / "security").mkdir(parents=True, exist_ok=True)

        # Set default config if not provided
        if config is None:
            config = ProfileConfig(profile_name=profile)
        else:
            config.profile_name = profile

        # Set profile-specific paths
        config.data_dir = str(profile_dir / "data")
        config.memory_db_path = str(profile_dir / "data" / "memory" / "memory.db")
        config.vector_db_path = str(profile_dir / "data" / "memory" / "vector_db")
        config.skills_dir = str(profile_dir / "data" / "skills")

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

        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)

        return ProfileConfig(**data)

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
