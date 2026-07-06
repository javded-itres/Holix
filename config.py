from core.env_loader import bootstrap_env
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

bootstrap_env()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    holix_env: str = Field(default="development", description="development | production")
    encryption_mode: str = Field(
        default="linux-production",
        validation_alias=AliasChoices(
            "HOLIX_ENCRYPTION_MODE",
            "HOLIX_ENCRYPTION_POLICY",
        ),
        description="off | linux-production | on",
    )

    # LLM Configuration
    model: str = "qwen2.5-coder:32b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    temperature: float = 0.7

    # Agent Configuration
    max_steps: int = 90
    agent_max_tokens: int = Field(
        default=8192,
        validation_alias=AliasChoices("HOLIX_AGENT_MAX_TOKENS", "AGENT_MAX_TOKENS"),
        description="Default max_tokens for ReAct agent steps (reasoning models need headroom)",
    )
    llm_step_timeout: float = 300.0
    data_dir: str = "data"
    context_window: int = 131072

    # LangGraph Configuration
    use_langgraph: bool = True
    execution_mode: str = "react"
    langgraph_checkpoint_db_path: str = "data/memory/checkpoints.db"

    # Sub-Agent Configuration
    enable_subagents: bool = True
    subagent_default_process_mode: str = "async"
    subagent_max_concurrent: int = 4
    subagent_process_timeout: float = 120.0
    subagent_heartbeat_interval: float = 5.0

    # Meta-Agent Configuration
    enable_meta_agent: bool = False

    # Self-Refinement Configuration
    enable_self_refinement: bool = False
    max_refinement_iterations: int = 2
    refinement_quality_threshold: float = 0.7

    # Evolution Configuration
    enable_evolution: bool = False
    evolution_auto_learn: bool = True

    # Confirmation / Safety Configuration
    auto_allow_threshold: str = "low"
    non_interactive: bool = False
    confirmation_timeout: int = 0  # 0 = wait indefinitely for user approval

    # Plan Review Configuration
    plan_review_enabled: bool = True
    plan_review_timeout: int = 600

    # Plan Execution Configuration
    max_steps_per_plan_step: int = 5
    plan_generation_timeout: float = 600.0
    plan_generation_retries: int = 2
    plan_generation_max_tokens: int = 12000

    # Memory Configuration
    memory_db_path: str = "data/memory/memory.db"
    vector_db_path: str = "data/memory/vector_db"
    ltm_db_path: str = "data/memory/ltm.db"
    enable_long_term_memory: bool = True
    auto_summarize_conversations: bool = True

    # Skills Configuration
    skills_dir: str = "data/skills"

    # Browser automation (Playwright)
    enable_browser_tools: bool = False
    browser_headless: bool = True
    browser_viewport_width: int = 1280
    browser_viewport_height: int = 720
    browser_allowed_hosts: str = ""

    # API Gateway
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8000
    gateway_with_docs: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "HOLIX_GATEWAY_WITH_DOCS",
            "HOLIX_GATEWAY_DOCS",
            "HELIX_GATEWAY_WITH_DOCS",
            "HELIX_GATEWAY_DOCS",
        ),
        description="Start documentation site together with holix gateway start",
    )
    docs_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("HOLIX_DOCS_HOST", "HELIX_DOCS_HOST"),
    )
    docs_port: int = Field(
        default=8080,
        validation_alias=AliasChoices("HOLIX_DOCS_PORT", "HELIX_DOCS_PORT"),
    )
    require_auth: bool = True
    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    api_keys_db_path: str = Field(
        default="security/api_keys.db",
        validation_alias=AliasChoices("HOLIX_API_KEYS_DB", "API_KEYS_DB"),
    )
    api_key_pepper: str = Field(
        default="",
        validation_alias=AliasChoices("HOLIX_API_KEY_PEPPER", "API_KEY_PEPPER"),
    )
    rate_limit_rpm: int = 100
    admin_rate_limit_rpm: int = 30
    public_rate_limit_rpm: int = 60
    enable_prometheus_metrics: bool = True

    # Documentation-site chat widget (isolated profile, no agent tools)
    docs_chat_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "HOLIX_DOCS_CHAT_ENABLED",
            "HELIX_DOCS_CHAT_ENABLED",
        ),
    )
    docs_chat_profile: str = Field(
        default="docs",
        validation_alias=AliasChoices(
            "HOLIX_DOCS_CHAT_PROFILE",
            "HELIX_DOCS_CHAT_PROFILE",
        ),
        description="Profile with LLM credentials for the public docs assistant only",
    )
    docs_chat_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "HOLIX_DOCS_CHAT_TOKEN",
            "HELIX_DOCS_CHAT_TOKEN",
        ),
        description="Shared token for docs server proxy → gateway (not exposed to browsers)",
    )
    docs_chat_rate_limit_rpm: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "HOLIX_DOCS_CHAT_RATE_LIMIT_RPM",
            "HELIX_DOCS_CHAT_RATE_LIMIT_RPM",
        ),
    )
    docs_chat_model: str = Field(
        default="",
        validation_alias=AliasChoices(
            "HOLIX_DOCS_CHAT_MODEL",
            "HELIX_DOCS_CHAT_MODEL",
        ),
        description="Optional model override for docs chat (use a non-reasoning model like smart)",
    )
    docs_chat_max_tokens: int = Field(
        default=4096,
        validation_alias=AliasChoices(
            "HOLIX_DOCS_CHAT_MAX_TOKENS",
            "HELIX_DOCS_CHAT_MAX_TOKENS",
        ),
    )

    # Tools (production hardening)
    enable_code_executor: bool = True
    enable_terminal_tool: bool = True
    terminal_command_whitelist: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "HOLIX_TERMINAL_COMMAND_WHITELIST",
            "TERMINAL_COMMAND_WHITELIST",
        ),
    )
    # Comma-separated extra base commands or prefixes (e.g. holix,uv run,docker)
    terminal_whitelist_extra: str = Field(
        default="",
        validation_alias=AliasChoices(
            "HOLIX_TERMINAL_WHITELIST_EXTRA",
            "TERMINAL_WHITELIST_EXTRA",
        ),
    )

    # Telegram
    telegram_require_allowlist_in_production: bool = True
    telegram_voice_enabled: bool = Field(
        default=True,
        validation_alias="HOLIX_TELEGRAM_VOICE_ENABLED",
    )
    telegram_voice_language: str = Field(
        default="",
        validation_alias="HOLIX_TELEGRAM_VOICE_LANGUAGE",
        description="Whisper language hint (ISO-639-1), empty = auto-detect",
    )
    telegram_files_enabled: bool = Field(
        default=True,
        validation_alias="HOLIX_TELEGRAM_FILES_ENABLED",
    )
    telegram_max_file_mb: int = Field(
        default=20,
        validation_alias="HOLIX_TELEGRAM_MAX_FILE_MB",
    )
    telegram_vision_model: str = Field(
        default="",
        validation_alias="HOLIX_TELEGRAM_VISION_MODEL",
        description="Vision model for Telegram images; empty = main agent model",
    )
    telegram_image_router_enabled: bool = Field(
        default=False,
        validation_alias="HOLIX_TELEGRAM_IMAGE_ROUTER_ENABLED",
        description="Helix-side image routing (off when LiteLLM vision-auto handles routing)",
    )
    telegram_media_group_delay_ms: int = Field(
        default=800,
        validation_alias="HOLIX_TELEGRAM_MEDIA_GROUP_DELAY_MS",
        description="Wait for all items in a Telegram album before processing",
    )

    # MAX messenger
    max_files_enabled: bool = Field(
        default=True,
        validation_alias="HELIX_MAX_FILES_ENABLED",
    )
    max_max_file_mb: int = Field(
        default=20,
        validation_alias="HELIX_MAX_MAX_FILE_MB",
    )

    # Whisper / voice transcription (Telegram)
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_BASE_URL"),
    )
    whisper_api_key: str = Field(
        default="",
        validation_alias="HOLIX_WHISPER_API_KEY",
        description="Override API key for transcription (e.g. LiteLLM virtual key)",
    )
    whisper_base_url: str = Field(
        default="",
        validation_alias="HOLIX_WHISPER_BASE_URL",
        description="Override base URL for transcription (e.g. http://host:4000/v1)",
    )
    whisper_use_profile_litellm: bool = Field(
        default=True,
        validation_alias="HOLIX_WHISPER_USE_PROFILE_LITELLM",
        description="Fallback to profile litellm provider when no whisper/openai keys set",
    )
    whisper_backend: str = Field(
        default="api",
        validation_alias="HOLIX_WHISPER_BACKEND",
        description="api | local | auto — auto picks local when faster-whisper installed and no API keys",
    )
    whisper_local_model: str = Field(
        default="base",
        validation_alias="HOLIX_WHISPER_LOCAL_MODEL",
        description="faster-whisper size: tiny, base, small, medium, large-v3, …",
    )
    whisper_local_device: str = Field(
        default="cpu",
        validation_alias="HOLIX_WHISPER_LOCAL_DEVICE",
        description="cpu | cuda | auto",
    )
    whisper_local_compute_type: str = Field(
        default="int8",
        validation_alias="HOLIX_WHISPER_LOCAL_COMPUTE_TYPE",
        description="CTranslate2 type: int8 (cpu), float16 (gpu), …",
    )
    whisper_auto_download: bool = Field(
        default=True,
        validation_alias="HOLIX_WHISPER_AUTO_DOWNLOAD",
        description="Pre-download local faster-whisper weights on Telegram bot startup",
    )
    whisper_local_download_root: str = Field(
        default="",
        validation_alias="HOLIX_WHISPER_LOCAL_DOWNLOAD_ROOT",
        description="Directory for faster-whisper model cache (default: ~/.holix/models/whisper)",
    )
    whisper_model: str = Field(
        default="whisper-1",
        validation_alias=AliasChoices("HOLIX_WHISPER_MODEL", "WHISPER_MODEL"),
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("HOLIX_LOG_LEVEL", "LOG_LEVEL"),
    )
    log_debug_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HOLIX_LOG_DEBUG", "LOG_DEBUG"),
    )
    log_max_bytes: int = Field(
        default=10_485_760,
        validation_alias=AliasChoices("HOLIX_LOG_MAX_BYTES", "LOG_MAX_BYTES"),
    )
    log_backup_count: int = Field(
        default=10,
        validation_alias=AliasChoices("HOLIX_LOG_BACKUP_COUNT", "LOG_BACKUP_COUNT"),
    )
    log_rotation_days: int = Field(
        default=14,
        validation_alias=AliasChoices("HOLIX_LOG_ROTATION_DAYS", "LOG_ROTATION_DAYS"),
    )

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.holix_env.strip().lower() == "production"

    @property
    def is_development(self) -> bool:
        return not self.is_production

    @property
    def effective_require_auth(self) -> bool:
        if self.is_production:
            return True
        return self.require_auth

    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw or raw == "*":
            return ["*"] if not self.is_production else []
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()