"""
Sub-Agent Registry — predefined sub-agent configurations.

Provides ready-to-use sub-agent types for common tasks:
- researcher: Deep information analysis
- web_researcher: Smart web search with query expansion and synthesis
- coder: Code generation and editing
- analyst: Data analysis and visualization
- reviewer: Code review and quality assessment
"""

from core.subagents.base import SubAgentConfig

_BUILTIN_NAMES: frozenset[str] | None = None

PREDEFINED_SUBAGENTS = {
    "researcher": SubAgentConfig(
        name="researcher",
        system_prompt=(
            "You are a research specialist. Your job is to analyze information deeply, "
            "search the web for relevant data, read files, and synthesize findings into "
            "clear, actionable insights. Focus on accuracy and thoroughness."
        ),
        tools=["web_search", "web_fetch", "read_file", "list_directory"],
        max_steps=12,
        mode="react",
        process_mode="async",
        temperature=0.3,
        description="Research specialist — analyzes information and searches for data",
        tags=["research", "analysis", "web"],
    ),

    "web_researcher": SubAgentConfig(
        name="web_researcher",
        system_prompt=(
            "You are an intelligent web research specialist. Your ONLY job is to search "
            "the web and synthesize findings.\n\n"
            "## Workflow\n"
            "1. Take the user's query and expand it into 3-5 varied search queries "
            "(different angles, synonyms, related terms).\n"
            "2. Execute web_search for each query variant.\n"
            "3. Read the most promising result pages with web_fetch when needed.\n"
            "4. Synthesize ALL results into a single coherent summary.\n\n"
            "## Rules\n"
            "- ALWAYS generate multiple query variants before searching.\n"
            "- Cite sources with URLs in your final answer.\n"
            "- If results conflict, present different viewpoints.\n"
            "- Return the synthesis in Russian unless the query is in English.\n"
            "- Do NOT delegate further — you are the final research node."
        ),
        tools=["web_search", "web_fetch"],
        max_steps=15,
        mode="react",
        process_mode="async",
        temperature=0.4,
        description="Smart web researcher — expands queries, searches, and synthesizes results",
        tags=["research", "web", "search", "synthesis"],
    ),

    "coder": SubAgentConfig(
        name="coder",
        system_prompt=(
            "You are a code generation specialist. Your job is to write, edit, "
            "and debug code. You can read existing files, write new ones, execute "
            "code for testing, and use the terminal for running commands. "
            "Always verify your code works before reporting completion."
        ),
        tools=["read_file", "write_file", "terminal", "code_executor"],
        max_steps=15,
        mode="react",
        process_mode="async",
        temperature=0.2,
        description="Code generation specialist — writes, edits, and debugs code",
        tags=["coding", "development", "debugging"],
    ),

    "analyst": SubAgentConfig(
        name="analyst",
        system_prompt=(
            "You are a data analysis specialist. Your job is to query databases, "
            "analyze data, perform calculations, and generate insights. You can "
            "execute SQL queries, run Python code, and use mathematical tools."
        ),
        tools=["sql_query", "sql_schema", "code_executor", "math_calculator"],
        max_steps=10,
        mode="react",
        process_mode="async",
        temperature=0.1,
        description="Data analysis specialist — queries databases and analyzes data",
        tags=["data", "analysis", "sql"],
    ),

    "reviewer": SubAgentConfig(
        name="reviewer",
        system_prompt=(
            "You are a code review specialist. Your job is to read code, identify "
            "bugs, security issues, performance problems, and style violations. "
            "Provide specific, actionable feedback with file paths and line numbers."
        ),
        tools=["read_file", "list_directory", "terminal"],
        max_steps=8,
        mode="react",
        process_mode="async",
        temperature=0.2,
        description="Code review specialist — identifies bugs and quality issues",
        tags=["review", "quality", "security"],
    ),

    "writer": SubAgentConfig(
        name="writer",
        system_prompt=(
            "You are a writing and documentation specialist. Your job is to create "
            "clear, well-structured documentation, comments, README files, and "
            "user guides. Focus on clarity, completeness, and proper formatting."
        ),
        tools=["read_file", "write_file", "list_directory"],
        max_steps=8,
        mode="react",
        process_mode="async",
        temperature=0.5,
        description="Writing specialist — creates documentation and content",
        tags=["documentation", "writing", "content"],
    ),
}


def builtin_subagent_names() -> frozenset[str]:
    global _BUILTIN_NAMES
    if _BUILTIN_NAMES is None:
        _BUILTIN_NAMES = frozenset(PREDEFINED_SUBAGENTS.keys())
    return _BUILTIN_NAMES


def is_builtin_subagent(name: str) -> bool:
    return (name or "").strip().lower() in builtin_subagent_names()


def _copy_config(original: SubAgentConfig) -> SubAgentConfig:
    return SubAgentConfig(
        name=original.name,
        agent_type=original.agent_type or original.name,
        system_prompt=original.system_prompt,
        model=original.model,
        tools=list(original.tools),
        max_steps=original.max_steps,
        mode=original.mode,
        process_mode=original.process_mode,
        timeout=original.timeout,
        memory_access=original.memory_access,
        temperature=original.temperature,
        description=original.description,
        tags=list(original.tags),
        mcp_servers=list(original.mcp_servers),
    )


def get_subagent_config(name: str, *, profile: str | None = None) -> SubAgentConfig:
    """Get a sub-agent configuration by type name (built-in or custom).

    Args:
        name: Sub-agent type name.
        profile: Active profile for custom type lookup.

    Returns:
        A copy of the SubAgentConfig.

    Raises:
        KeyError: If no sub-agent with this name exists.
    """
    slug = (name or "").strip().lower()
    if slug in PREDEFINED_SUBAGENTS:
        return _copy_config(PREDEFINED_SUBAGENTS[slug])

    if profile:
        from core.subagents.store import SubAgentTypeStore

        custom = SubAgentTypeStore(profile).get(slug)
        if custom is not None:
            return _copy_config(custom.to_subagent_config())

    available = ", ".join(n["name"] for n in list_available_subagents(profile=profile))
    raise KeyError(f"No sub-agent '{name}'. Available: {available}")


def list_available_subagents(*, profile: str | None = None) -> list[dict]:
    """List built-in and profile custom sub-agent types."""
    items = [
        {
            "name": config.name,
            "description": config.description,
            "tools": config.tools,
            "tags": list(config.tags),
            "builtin": True,
        }
        for config in PREDEFINED_SUBAGENTS.values()
    ]
    if profile:
        from core.subagents.store import SubAgentTypeStore

        for custom in SubAgentTypeStore(profile).load_types().values():
            items.append(
                {
                    "name": custom.name,
                    "description": custom.description,
                    "tools": custom.tools,
                    "tags": ["custom"],
                    "builtin": False,
                }
            )
    return items


def subagent_type_names(*, profile: str | None = None) -> frozenset[str]:
    return frozenset(item["name"] for item in list_available_subagents(profile=profile))
