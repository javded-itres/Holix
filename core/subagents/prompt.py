"""System prompt assembly for sub-agents."""

from __future__ import annotations

from core.project.holix_md import append_holix_project_context
from core.prompt_builder import (
    format_studio_workspace_block,
    format_working_directory_block,
    language_instruction_block,
    resolve_agent_working_directory,
)
from core.subagents.base import SubAgentConfig


def build_subagent_system_prompt(
    config: SubAgentConfig,
    task: str,
    *,
    skills_block: str = "",
    profile_name: str | None = None,
    workspace_root: str | None = None,
    workspace_jail_enabled: bool | None = None,
    working_directory: str | None = None,
) -> str:
    """Build sub-agent system prompt with the same workspace as the main agent."""
    lang_block = language_instruction_block(profile_name=profile_name)
    base = config.system_prompt or f"You are {config.name}, a specialized AI assistant."

    prompt = f"""{lang_block}

{base}

## Your Task
{task}

## Available Tools
{", ".join(config.tools) if config.tools else "No tools available"}

## Instructions
1. Focus on your specific task
2. Use tools when needed to gather information or take action
3. Provide a clear, concise final answer
4. If you cannot complete the task, explain why
5. File paths and shell commands run in the shared working directory below — same as the main agent
6. When automated tests already pass, stop calling tools and write the final answer so the parent process can continue. Do not re-run the same passing pytest.
"""
    if getattr(config, "fork", False):
        prompt += (
            "\n## Forked parent context\n"
            "Messages before your task are completed turns from the parent "
            "conversation (a snapshot, not live). You do not share the parent's "
            "tools, PTY, todos, or permission preset.\n"
        )
    prompt += f"""
Remember: You are {config.name}. Stay focused on your specialized role.
"""
    if skills_block:
        prompt += f"\n\n{skills_block}"

    studio = format_studio_workspace_block(
        workspace_root=workspace_root,
        workspace_jail_enabled=workspace_jail_enabled,
    )
    if studio:
        prompt = f"{prompt.rstrip()}\n\n{studio}"
    else:
        wd = format_working_directory_block(
            workspace_root=workspace_root,
            workspace_jail_enabled=workspace_jail_enabled,
            working_directory=working_directory,
        )
        if wd:
            prompt = f"{prompt.rstrip()}\n\n{wd}"

    project_cwd = resolve_agent_working_directory(
        workspace_root=workspace_root,
        workspace_jail_enabled=workspace_jail_enabled,
        working_directory=working_directory,
    )
    return append_holix_project_context(prompt, cwd=project_cwd)
