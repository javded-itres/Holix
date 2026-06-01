from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Configuration
    model: str = "qwen2.5-coder:32b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    temperature: float = 0.7

    # Agent Configuration
    max_steps: int = 15
    data_dir: str = "data"

    # Memory Configuration
    memory_db_path: str = "data/memory/memory.db"
    vector_db_path: str = "data/memory/vector_db"

    # Skills Configuration
    skills_dir: str = "data/skills"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


settings = Settings()
