"""System prompt assembly for sub-agents."""

from __future__ import annotations

from core.project.holix_md import append_holix_project_context
from core.prompt_builder import (
    format_studio_workspace_block,
    format_working_directory_block,
    language_instruction_block,
    resolve_prompt_context_directory,
)
from core.subagents.base import SubAgentConfig


def subagent_language_lock(*, profile_name: str | None) -> str:
    """Repeat the UI language after the task so questions do not follow English briefs."""
    from core.i18n.locale import LocaleStore, normalize_locale

    locale = "ru"
    if profile_name:
        try:
            locale = normalize_locale(LocaleStore(profile_name).get())
        except Exception:
            locale = "ru"
    if locale == "en":
        return (
            "## Questions language\n"
            "The selected interface language is English. "
            "Write every question to the user and to the parent, including "
            "`ask_user` prompts, option labels, and headers, in English. "
            "Do this even when the task text or this system prompt is in another language."
        )
    return (
        "## Язык вопросов\n"
        "Выбранный язык интерфейса — русский. "
        "Все вопросы человеку и родителю, тексты `ask_user`, подписи вариантов "
        "и заголовки пиши по-русски. "
        "Не переключайся на английский из-за того, что задача или этот промпт "
        "сформулированы на английском."
    )


def build_subagent_system_prompt(
    config: SubAgentConfig,
    task: str,
    *,
    skills_block: str = "",
    profile_name: str | None = None,
    workspace_root: str | None = None,
    workspace_jail_enabled: bool | None = None,
    working_directory: str | None = None,
    documents_block: str | None = None,
) -> str:
    """Build sub-agent system prompt with the same workspace as the main agent."""
    lang_block = language_instruction_block(profile_name=profile_name)
    base = config.system_prompt or f"You are {config.name}, a specialized AI assistant."

    if documents_block is None:
        from core.subagents.session_documents import attach_session_documents

        documents_block = attach_session_documents(config, profile_name)

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
    if documents_block:
        prompt += f"\n{documents_block}\n"
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

    try:
        from core.sdd.change_workspace import (
            format_active_change_prompt_block,
            get_active_change,
        )

        cid = str(getattr(config, "conversation_id", None) or "").strip()
        parent_cid = str(getattr(config, "parent_conversation_id", None) or "").strip()
        prof = (profile_name or "default").strip() or "default"
        active = get_active_change(prof, cid) if cid else None
        if active is None and parent_cid:
            active = get_active_change(prof, parent_cid)
        change_block = format_active_change_prompt_block(active)
        if change_block:
            prompt = f"{prompt.rstrip()}\n\n{change_block}"
    except Exception:
        pass

    project_cwd = resolve_prompt_context_directory(
        workspace_root=workspace_root,
        workspace_jail_enabled=workspace_jail_enabled,
        working_directory=working_directory,
    )
    prompt = append_holix_project_context(prompt, cwd=project_cwd)
    return f"{prompt.rstrip()}\n\n{subagent_language_lock(profile_name=profile_name)}\n"
