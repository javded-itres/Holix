"""Slash command registry (shared by TUI and Telegram)."""

from __future__ import annotations

from pathlib import Path

from core.i18n.messages import t

_STATIC_SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show help"),
    ("/status", "Profile, mode, session"),
    ("/clear", "Clear transcript"),
    ("/metrics", "Show metrics"),
    ("/compress", "Compress conversation context"),
    ("/forget", "Clear session memory"),
    ("/init", "Write .holix/HOLIX.md"),
    ("/commands", "Custom commands: list | reload"),
    ("/stream", "Toggle streaming"),
    ("/mode", "Cycle execution mode"),
    ("/models", "Switch LLM model"),
    ("/stop", "Stop the running agent turn"),
    ("/process", "Background processes: list | stop"),
    ("/todos", "Session checklist"),
    ("/trace", "Session trajectory"),
    ("/permission", "OS sandbox preset"),
    ("/pty", "Persistent shell: on | off | reset"),
    ("/change", "SDD worktree: list | switch | leave"),
    ("/new", "New session"),
    ("/sessions", "List sessions"),
    ("/switch", "Switch session by number"),
    ("/session", "Rename current session"),
    ("/profile", "Switch profile"),
    ("/memory", "Search memory | clear"),
    ("/last", "Current work and last tool output"),
    ("/tools", "Recent tool results"),
    ("/copy", "Copy: last | tool | all"),
    ("/open", "Open transcript"),
    ("/yes", "Allow once"),
    ("/no", "Deny"),
    ("/plan", "Plan review: confirm | auto | refine | reject"),
    ("/mcp", "MCP: list | install | add | test | tools | remove"),
    ("/search", "Web search: list | configure | test"),
    ("/hub", "Skill catalogs: installed | browse"),
    ("/skill", "Run a skill"),
    ("/skills", "Skills: list | pending | quality | curator"),
    ("/learn", "Draft a skill from a source"),
    ("/launch", "External CLIs in tmux"),
    ("/cron", "Scheduled jobs"),
    ("/spec", "SDD specs and changes"),
    ("/subagents", "Sub-agents: list | spawn | result | stop | types"),
    ("/lang", "Interface language (en / ru)"),
]

SLASH_COMMANDS: list[tuple[str, str]] = list(_STATIC_SLASH_COMMANDS)


def slash_commands_for_locale(locale: str | None = None) -> list[tuple[str, str]]:
    """Static slash commands with localized /lang description."""
    loc = locale or "en"
    out: list[tuple[str, str]] = []
    for cmd, desc in _STATIC_SLASH_COMMANDS:
        if cmd == "/lang":
            out.append((cmd, t("lang.cmd_desc", loc)))
        else:
            out.append((cmd, desc))
    return out


def all_slash_commands(
    skills_dir: Path | None = None,
    *,
    agent_slot: str = "main",
    skill_assignments: dict | None = None,
    locale: str | None = None,
) -> list[tuple[str, str]]:
    """Static commands plus custom markdown commands and hub skill slashes."""
    out = slash_commands_for_locale(locale)
    try:
        from core.commands.help import custom_slash_pairs

        seen = {c.split()[0] for c, _ in out}
        for cmd, desc in custom_slash_pairs():
            token = cmd.split()[0]
            if token not in seen:
                out.append((cmd, desc))
                seen.add(token)
    except Exception:
        pass
    if skills_dir is None:
        return out
    try:
        from core.hub.slash_registry import load_skill_slash_commands

        seen = {c for c, _ in out}
        for cmd, desc in load_skill_slash_commands(
            skills_dir,
            agent_slot=agent_slot,
            skill_assignments=skill_assignments,
        ):
            if cmd not in seen:
                out.append((cmd, desc))
                seen.add(cmd)
    except Exception:
        pass
    try:
        from core.extensions.agent_registry import agent_slash_commands

        seen = {c for c, _ in out}
        for spec in agent_slash_commands():
            if spec.command not in seen:
                out.append((spec.command, spec.description))
                seen.add(spec.command)
    except Exception:
        pass
    return out
