"""System prompt assembly for sub-agents."""

from __future__ import annotations

from core.project.holix_md import append_holix_project_context
from core.prompt_builder import language_instruction_block
from core.subagents.base import SubAgentConfig


def build_subagent_system_prompt(
    config: SubAgentConfig,
    task: str,
    *,
    skills_block: str = "",
    profile_name: str | None = None,
) -> str:
    """Build sub-agent system prompt with profile UI locale (en / ru)."""
    lang_block = language_instruction_block(profile_name=profile_name)
    base = config.system_prompt or f"You are {config.name}, a specialized AI assistant."

    prompt = f"""{lang_block}

{base}

## Your Task
{task}

## Available Tools
{', '.join(config.tools) if config.tools else 'No tools available'}

## Instructions
1. Focus on your specific task
2. Use tools when needed to gather information or take action
3. Provide a clear, concise final answer
4. If you cannot complete the task, explain why

Remember: You are {config.name}. Stay focused on your specialized role.
"""
    if skills_block:
        prompt += f"\n\n{skills_block}"
    return append_holix_project_context(prompt)