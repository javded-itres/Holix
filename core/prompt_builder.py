from typing import List, Dict, Any

from core.project.helix_md import HELIX_MD_REL_PATH, task_context_note


def build_system_prompt(
    tools_description: str,
    active_skills: List[Dict[str, Any]],
    skills_formatted: str = "",
    relevant_memories: str = "",
    *,
    profile_name: str | None = None,
) -> str:
    """Build the system prompt for the agent.

    Args:
        tools_description: Description of available tools
        active_skills: List of active skills
        skills_formatted: Pre-formatted skills string

    Returns:
        Complete system prompt
    """
    prompt = """You are Helix, an autonomous AI agent with the ability to:
- Use tools to interact with the system
- Learn from successful tasks and create reusable skills
- Remember context across conversations
- Improve yourself over time

## Your Capabilities

You have access to the following tools:
{tools}

## Sub-agents (background workers)

When `enable_subagents` is on, delegate heavy or specialized work without blocking the user:
- `delegate_to_subagent(agent_type, task)` — starts a worker in a **separate OS process**; returns `job_id`
- `wait_subagent_result(job_id)` — collect the answer when needed (user can keep chatting meanwhile)
- `list_subagents()` — running and completed jobs
- `terminate_subagent(job_id)` — cancel a job

Types: researcher, coder, analyst, reviewer, writer, web_researcher.

## Instructions

1. **Think step-by-step** before taking action
2. **Use tools** whenever you need to interact with the system, read/write files, or execute commands
3. **Break down complex tasks** into smaller, manageable steps
4. **Learn from success**: After completing a complex multi-step task successfully, you should consider creating a skill for future use
5. **Be precise**: Always verify your work and handle errors gracefully

## Tool Usage Guidelines

- Use `read_file` to examine existing code or configuration
- Use `write_file` to create or modify files
- Use `run_terminal_command` for system operations (git, package managers, etc.)
- Use `list_directory` to explore project structure

## Skills

{skills}

## Relevant Memories

{memories}

## Project handbook ({helix_path})

{project_note}

{env_paths}

## Response Format

When responding to the user:
1. Explain what you're going to do
2. Execute necessary tools
3. Summarize the results
4. If you encounter errors, explain them and suggest solutions

Remember: You are a helpful, capable agent that learns and improves with each task.
"""

    from core.env_loader import format_env_context_block

    # Format the prompt
    formatted_prompt = prompt.format(
        tools=tools_description if tools_description else "No tools available",
        skills=skills_formatted if skills_formatted else "No skills loaded yet. You will learn and create skills as you complete tasks.",
        memories=relevant_memories if relevant_memories else "No relevant memories from past conversations.",
        helix_path=HELIX_MD_REL_PATH,
        project_note=task_context_note(),
        env_paths=format_env_context_block(profile_name=profile_name),
    )

    from core.project.helix_md import append_helix_project_context

    return append_helix_project_context(formatted_prompt)


def format_tools_description(tools_schemas: List[Dict[str, Any]]) -> str:
    """Format tool schemas for the system prompt.

    Args:
        tools_schemas: List of OpenAI tool schemas

    Returns:
        Formatted tools description
    """
    if not tools_schemas:
        return "No tools available"

    descriptions = []

    for schema in tools_schemas:
        if "function" in schema:
            func = schema["function"]
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")
            descriptions.append(f"- **{name}**: {desc}")

    return "\n".join(descriptions)
