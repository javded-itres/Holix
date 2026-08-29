"""Immutable runtime configuration for Holix (replaces global settings mutation)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from config import Settings
from config import settings as default_settings

try:
    from typing import Self
except ImportError:  # py < 3.11
    from typing import Self  # type: ignore[assignment]

if TYPE_CHECKING:
    from core.profile import ProfileConfig

_DEFAULT_CHECKPOINT_MAX_BYTES = 200 * 1024 * 1024


def _checkpoint_max_bytes_from_settings(s: Settings | Any) -> int:
    """Convert Settings.checkpoint_max_mb to bytes (0 disables prune)."""
    try:
        mb = int(getattr(s, "checkpoint_max_mb", 200) or 0)
    except (TypeError, ValueError):
        mb = 200
    if mb <= 0:
        return 0
    return mb * 1024 * 1024


@dataclass(frozen=True, slots=True)
class HolixRuntimeConfig:
    """Resolved configuration for a single agent / session."""

    # LLM
    model: str
    base_url: str
    api_key: str
    temperature: float

    # Agent
    max_steps: int
    llm_step_timeout: float
    data_dir: str
    context_window: int

    # LangGraph
    use_langgraph: bool
    execution_mode: str
    langgraph_checkpoint_db_path: str

    # Sub-agents
    enable_subagents: bool
    subagent_default_process_mode: str
    subagent_max_concurrent: int
    subagent_process_timeout: float
    subagent_heartbeat_interval: float
    subagent_supervisor_enabled: bool
    subagent_supervisor_poll_s: float
    subagent_supervisor_idle_s: float
    subagent_supervisor_max_interventions: int
    subagent_supervisor_cooldown_s: float
    subagent_supervisor_loop_cooldown_s: float

    # Meta-agent / refinement / evolution
    enable_meta_agent: bool
    enable_self_refinement: bool
    max_refinement_iterations: int
    refinement_quality_threshold: float
    enable_evolution: bool
    evolution_auto_learn: bool

    # Step budget auto-extension when agent is still making progress
    max_steps_extend_enabled: bool
    max_steps_extend_by: int
    max_steps_max_extensions: int
    max_steps_hard_cap: int

    # Safety / plan review
    auto_allow_threshold: str
    non_interactive: bool
    confirmation_timeout: int
    plan_review_enabled: bool
    plan_review_timeout: int

    # Plan execution
    max_steps_per_plan_step: int
    plan_generation_timeout: float
    plan_generation_retries: int
    plan_generation_max_tokens: int

    # Memory / skills paths
    memory_db_path: str
    vector_db_path: str
    memory_chroma_collection: str
    ltm_db_path: str
    enable_long_term_memory: bool
    auto_summarize_conversations: bool
    skills_dir: str

    # Browser (Playwright)
    enable_browser_tools: bool
    browser_headless: bool
    browser_viewport_width: int
    browser_viewport_height: int
    browser_allowed_hosts: str

    # Profile metadata (optional)
    profile_name: str = "default"
    # Response pipeline: classic (≈1.0.2) | modern (anti-monologue)
    agent_pipeline: str = "classic"
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    # MCP servers (defs + assignments). Only additive from profile; local .helix may supplement at load time.
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    mcp_assignments: dict[str, list[str]] = field(default_factory=dict)
    mcp_enabled: bool = True

    skill_assignments: dict[str, list[str]] = field(default_factory=dict)

    # Web search (DuckDuckGo / SearXNG / Firecrawl)
    search: dict[str, Any] = field(default_factory=dict)

    # Local project supplement dir (CWD/.holix) — used for skills, plans, extra mcp; NEVER for model/system keys.
    local_project_dir: str = ".holix"
    local_skills_dir: str | None = None  # resolved at use site if None

    # Workspace jail (optional per-profile directory isolation)
    workspace_jail_enabled: bool = False
    workspace_root: str | None = None
    tools_presentation: str = "native"
    tools_presentation_by_slot: dict[str, str] = field(default_factory=dict)
    code_mode_wall_timeout_s: int = 120
    code_mode_max_inner_calls: int = 40
    code_mode_parallel_readonly: bool = True
    encryption_enabled: bool = False

    # Self-authored drop-in agent extensions (local single-operator only)
    # False for Telegram/MAX multi-user agents.
    self_extensions_enabled: bool = True

    # LangGraph checkpoint size guard (bytes; 0 = never auto-reset)
    checkpoint_auto_prune: bool = True
    checkpoint_max_bytes: int = 200 * 1024 * 1024

    # Vector store: chroma (on-disk) | pgvector | memory
    vector_backend: str = "chroma"
    vector_dsn: str = ""
    vector_dim: int = 384
    vector_table: str = "holix_vectors"

    @classmethod
    def from_settings(cls, source: Settings | None = None) -> Self:
        """Build config from pydantic Settings (env / .env).

        Prefer a fresh ``Settings()`` so profile ``.env`` loaded after process
        start (``bootstrap_profile_env``) is visible. The module-level
        ``config.settings`` singleton is frozen at first import.
        """
        if source is not None:
            s = source
        else:
            try:
                s = Settings(_env_file=None)
            except Exception:
                s = default_settings
        return cls(
            model=s.model,
            base_url=s.base_url,
            api_key=s.api_key,
            temperature=s.temperature,
            max_steps=s.max_steps,
            llm_step_timeout=s.llm_step_timeout,
            data_dir=s.data_dir,
            context_window=s.context_window,
            use_langgraph=s.use_langgraph,
            execution_mode=s.execution_mode,
            langgraph_checkpoint_db_path=s.langgraph_checkpoint_db_path,
            checkpoint_auto_prune=bool(getattr(s, "checkpoint_auto_prune", True)),
            checkpoint_max_bytes=_checkpoint_max_bytes_from_settings(s),
            enable_subagents=s.enable_subagents,
            subagent_default_process_mode=s.subagent_default_process_mode,
            subagent_max_concurrent=s.subagent_max_concurrent,
            subagent_process_timeout=s.subagent_process_timeout,
            subagent_heartbeat_interval=s.subagent_heartbeat_interval,
            subagent_supervisor_enabled=bool(getattr(s, "subagent_supervisor_enabled", True)),
            subagent_supervisor_poll_s=float(getattr(s, "subagent_supervisor_poll_s", 4.0) or 4.0),
            subagent_supervisor_idle_s=float(
                getattr(s, "subagent_supervisor_idle_s", 300.0) or 300.0
            ),
            subagent_supervisor_max_interventions=int(
                getattr(s, "subagent_supervisor_max_interventions", 3) or 3
            ),
            subagent_supervisor_cooldown_s=float(
                getattr(s, "subagent_supervisor_cooldown_s", 45.0) or 45.0
            ),
            subagent_supervisor_loop_cooldown_s=float(
                getattr(s, "subagent_supervisor_loop_cooldown_s", 8.0) or 8.0
            ),
            enable_meta_agent=s.enable_meta_agent,
            enable_self_refinement=s.enable_self_refinement,
            max_refinement_iterations=s.max_refinement_iterations,
            refinement_quality_threshold=s.refinement_quality_threshold,
            enable_evolution=s.enable_evolution,
            evolution_auto_learn=s.evolution_auto_learn,
            agent_pipeline=str(getattr(s, "agent_pipeline", "classic") or "classic"),
            max_steps_extend_enabled=bool(getattr(s, "max_steps_extend_enabled", True)),
            max_steps_extend_by=int(getattr(s, "max_steps_extend_by", 30) or 30),
            max_steps_max_extensions=int(getattr(s, "max_steps_max_extensions", 10) or 10),
            max_steps_hard_cap=int(getattr(s, "max_steps_hard_cap", 0) or 0),
            auto_allow_threshold=s.auto_allow_threshold,
            non_interactive=s.non_interactive,
            confirmation_timeout=s.confirmation_timeout,
            plan_review_enabled=s.plan_review_enabled,
            plan_review_timeout=s.plan_review_timeout,
            max_steps_per_plan_step=s.max_steps_per_plan_step,
            plan_generation_timeout=s.plan_generation_timeout,
            plan_generation_retries=s.plan_generation_retries,
            plan_generation_max_tokens=s.plan_generation_max_tokens,
            memory_db_path=s.memory_db_path,
            vector_db_path=s.vector_db_path,
            memory_chroma_collection="memory",
            ltm_db_path=s.ltm_db_path,
            enable_long_term_memory=s.enable_long_term_memory,
            auto_summarize_conversations=s.auto_summarize_conversations,
            skills_dir=s.skills_dir,
            enable_browser_tools=s.enable_browser_tools,
            browser_headless=s.browser_headless,
            browser_viewport_width=s.browser_viewport_width,
            browser_viewport_height=s.browser_viewport_height,
            browser_allowed_hosts=s.browser_allowed_hosts,
            mcp_servers={},
            mcp_assignments={},
            mcp_enabled=True,
            skill_assignments={},
            search={},
            local_project_dir=".holix",
            local_skills_dir=None,
            workspace_jail_enabled=False,
            workspace_root=None,
            tools_presentation="native",
            tools_presentation_by_slot={},
            code_mode_wall_timeout_s=120,
            code_mode_max_inner_calls=40,
            code_mode_parallel_readonly=True,
            encryption_enabled=False,
            vector_backend=str(getattr(s, "vector_backend", "chroma") or "chroma"),
            vector_dsn=str(getattr(s, "vector_dsn", "") or ""),
            vector_dim=int(getattr(s, "vector_dim", 384) or 384),
            vector_table=str(getattr(s, "vector_table", "") or "holix_vectors"),
        )

    @classmethod
    def from_profile(
        cls,
        profile: ProfileConfig,
        *,
        base: Self | None = None,
    ) -> Self:
        """Merge CLI profile overrides onto a base config."""
        cfg = base or cls.from_settings()
        overrides: dict = {"profile_name": profile.profile_name}

        if profile.model:
            overrides["model"] = profile.model
        if profile.base_url:
            overrides["base_url"] = profile.base_url
        if profile.api_key:
            overrides["api_key"] = profile.api_key
        if profile.temperature is not None:
            overrides["temperature"] = profile.temperature
        if profile.max_steps is not None:
            overrides["max_steps"] = profile.max_steps
        from core.profile import ProfileManager, resolve_profile_storage_paths

        profile = resolve_profile_storage_paths(
            profile.profile_name,
            profile,
            profile_dir=ProfileManager().get_profile_dir(profile.profile_name),
        )
        overrides["skills_dir"] = profile.skills_dir
        overrides["data_dir"] = profile.data_dir
        overrides["memory_db_path"] = profile.memory_db_path
        overrides["vector_db_path"] = profile.vector_db_path
        overrides["ltm_db_path"] = profile.ltm_db_path
        overrides["langgraph_checkpoint_db_path"] = profile.langgraph_checkpoint_db_path
        if profile.context_window is not None:
            overrides["context_window"] = profile.context_window

        if getattr(profile, "mcp_servers", None):
            overrides["mcp_servers"] = profile.mcp_servers
        if getattr(profile, "mcp_assignments", None):
            overrides["mcp_assignments"] = profile.mcp_assignments
        if hasattr(profile, "mcp_enabled"):
            overrides["mcp_enabled"] = profile.mcp_enabled
        if getattr(profile, "skill_assignments", None):
            overrides["skill_assignments"] = profile.skill_assignments
        if getattr(profile, "enable_subagents", None) is not None:
            overrides["enable_subagents"] = profile.enable_subagents
        if getattr(profile, "subagent_default_process_mode", None):
            overrides["subagent_default_process_mode"] = profile.subagent_default_process_mode
        if getattr(profile, "subagent_max_concurrent", None) is not None:
            overrides["subagent_max_concurrent"] = profile.subagent_max_concurrent
        if getattr(profile, "subagent_supervisor_enabled", None) is not None:
            overrides["subagent_supervisor_enabled"] = bool(profile.subagent_supervisor_enabled)
        for _sk in (
            "subagent_supervisor_poll_s",
            "subagent_supervisor_idle_s",
            "subagent_supervisor_max_interventions",
            "subagent_supervisor_cooldown_s",
            "subagent_supervisor_loop_cooldown_s",
        ):
            _sv = getattr(profile, _sk, None)
            if _sv is not None:
                overrides[_sk] = _sv
        if getattr(profile, "enable_meta_agent", None) is not None:
            overrides["enable_meta_agent"] = bool(profile.enable_meta_agent)
        if getattr(profile, "enable_self_refinement", None) is not None:
            overrides["enable_self_refinement"] = bool(profile.enable_self_refinement)
        if getattr(profile, "agent_pipeline", None):
            from core.agent_pipeline import normalize_pipeline

            overrides["agent_pipeline"] = normalize_pipeline(str(profile.agent_pipeline))
        if getattr(profile, "max_steps_extend_enabled", None) is not None:
            overrides["max_steps_extend_enabled"] = bool(profile.max_steps_extend_enabled)
        if getattr(profile, "max_steps_extend_by", None) is not None:
            overrides["max_steps_extend_by"] = int(profile.max_steps_extend_by)
        if getattr(profile, "max_steps_max_extensions", None) is not None:
            overrides["max_steps_max_extensions"] = int(profile.max_steps_max_extensions)
        if getattr(profile, "max_steps_hard_cap", None) is not None:
            overrides["max_steps_hard_cap"] = int(profile.max_steps_hard_cap)
        if getattr(profile, "search", None):
            overrides["search"] = profile.search
        overrides["workspace_jail_enabled"] = bool(
            getattr(profile, "workspace_jail_enabled", False)
        )
        if getattr(profile, "workspace_root", None):
            overrides["workspace_root"] = profile.workspace_root
        from core.tools.code_mode.policy import normalize_presentation

        overrides["tools_presentation"] = normalize_presentation(
            getattr(profile, "tools_presentation", None)
        )
        slot_map = getattr(profile, "tools_presentation_by_slot", None) or {}
        if isinstance(slot_map, dict) and slot_map:
            overrides["tools_presentation_by_slot"] = {
                str(k).strip().lower(): normalize_presentation(v)
                for k, v in slot_map.items()
                if str(k).strip()
            }
        from core.tools.code_mode.policy import (
            DEFAULT_PARALLEL_READONLY,
            clamp_max_inner_calls,
            clamp_wall_timeout_s,
        )

        if getattr(profile, "code_mode_wall_timeout_s", None) is not None:
            overrides["code_mode_wall_timeout_s"] = clamp_wall_timeout_s(
                profile.code_mode_wall_timeout_s
            )
        if getattr(profile, "code_mode_max_inner_calls", None) is not None:
            overrides["code_mode_max_inner_calls"] = clamp_max_inner_calls(
                profile.code_mode_max_inner_calls
            )
        if getattr(profile, "code_mode_parallel_readonly", None) is not None:
            overrides["code_mode_parallel_readonly"] = bool(profile.code_mode_parallel_readonly)
        else:
            overrides.setdefault("code_mode_parallel_readonly", DEFAULT_PARALLEL_READONLY)
        if getattr(profile, "encryption_enabled", False):
            overrides["encryption_enabled"] = profile.encryption_enabled
        if getattr(profile, "auto_allow_threshold", None):
            overrides["auto_allow_threshold"] = str(profile.auto_allow_threshold)

        if profile.default_provider and profile.providers:
            pdata = profile.providers.get(profile.default_provider) or {}
            if pdata.get("metadata"):
                overrides["provider_metadata"] = dict(pdata["metadata"])
            if pdata.get("base_url") and not profile.base_url:
                overrides["base_url"] = pdata["base_url"]
            if pdata.get("api_key") and profile.api_key in ("", "ollama", "dummy"):
                overrides["api_key"] = pdata["api_key"]
            if pdata.get("default_model") and profile.model:
                pass
            elif pdata.get("default_model"):
                overrides["model"] = pdata["default_model"]

        return replace(cfg, **overrides)

    def with_overrides(self, **kwargs) -> Self:
        """Return a copy with selective field overrides."""
        valid = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **valid)


def unattended_requested() -> bool:
    """True when env or Settings asks for unattended (bench/CI) tool policy."""
    import os

    raw = (
        (os.environ.get("HOLIX_UNATTENDED") or os.environ.get("HOLIX_BENCH") or "").strip().lower()
    )
    if raw in {"1", "true", "yes", "on"}:
        return True
    try:
        from config import Settings

        return bool(getattr(Settings(_env_file=None), "holix_unattended", False))
    except Exception:
        return False


def apply_unattended_policy(cfg: HolixRuntimeConfig) -> HolixRuntimeConfig:
    """Force no interactive tool/plan confirmations for benches / CI.

    Sets ``auto_allow_threshold=high`` (all tool risks auto-run) and disables
    plan review. Does **not** set ``non_interactive`` — that would *deny*
    high-risk tools instead of approving them.

    ActionGuard still logs ``auto_allowed`` at INFO (audit only, no UI).
    """
    if not unattended_requested():
        return cfg
    return cfg.with_overrides(
        auto_allow_threshold="high",
        plan_review_enabled=False,
        non_interactive=False,
    )
