"""Slash command registry (shared by TUI and Telegram)."""

from __future__ import annotations

from pathlib import Path

from core.i18n.messages import t

_STATIC_SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show help"),
    ("/status", "Profile, mode, session status"),
    ("/clear", "Clear transcript"),
    ("/metrics", "Show metrics"),
    ("/compress", "Compress conversation context (free context window)"),
    ("/forget", "Clear session memory (DB + search index)"),
    ("/memory wipe", "Clear session memory (alias)"),
    ("/init", "Deep project analysis → .holix/HOLIX.md"),
    ("/commands", "List custom slash commands (.holix/commands)"),
    ("/commands reload", "Rescan custom command markdown files"),
    ("/stream", "Toggle streaming"),
    ("/mode", "Cycle execution mode"),
    ("/models", "Switch LLM model (runtime)"),
    ("/model", "Switch LLM model (alias)"),
    ("/stop", "Stop running tasks"),
    ("/process-stop", "Stop background dev server / long-running process"),
    ("/process", "List background processes for this session"),
    ("/todos", "Show the session checklist"),
    ("/new", "New session"),
    ("/sessions", "List sessions"),
    ("/switch", "Switch session by number"),
    ("/session", "Rename current session"),
    ("/profile", "Switch profile"),
    ("/memory", "Semantic memory search"),
    ("/memory-clear", "Clear memory search"),
    ("/last", "Full last tool output"),
    ("/tools", "Recent tool results"),
    ("/copy", "Copy last assistant (or selection)"),
    ("/copy tool", "Copy last tool output"),
    ("/copy all", "Copy full transcript"),
    ("/open", "Open transcript for select & copy"),
    ("/yes", "Allow once (confirm)"),
    ("/no", "Deny (confirm)"),
    ("/1", "Allow once"),
    ("/2", "Allow session"),
    ("/3", "Allow always"),
    ("/4", "Deny"),
    ("/plan-confirm", "Confirm plan"),
    ("/plan-auto", "Auto-run plan"),
    ("/plan-refine", "Refine plan"),
    ("/plan-reject", "Reject plan"),
    ("/mcp", "MCP servers menu / list"),
    ("/mcp list", "List configured MCP servers"),
    ("/mcp install", "Install popular MCP or from git URL"),
    ("/mcp add", "Manually add MCP server config"),
    ("/mcp assign", "Assign MCP servers to agents/subs"),
    ("/mcp test", "Test connection to an MCP server"),
    ("/mcp tools", "List currently available MCP tools"),
    ("/mcp remove", "Remove an MCP server configuration"),
    ("/search", "List configured web search providers"),
    ("/search configure", "Setup DuckDuckGo / SearXNG / Firecrawl"),
    ("/search test", "Test search with a query"),
    ("/hub", "Pick skill catalog (ClawHub, Hermes, Claude…)"),
    ("/hub installed", "List installed hub skills, plugins & MCP"),
    ("/hub list", "Same as /hub installed"),
    ("/hub browse", "Browse & install skills/plugins"),
    ("/hub clawhub", "Open ClawHub catalog"),
    ("/hub hermes", "Open HermesHub catalog"),
    ("/hub claude", "Open Claude official plugins"),
    ("/hub skills-sh", "Search skills.sh (needs query in browser)"),
    ("/skill", "Run a skill: /skill <name> [args]"),
    ("/skills", "Skills: holix skills list --agent <role>"),
    ("/skills pending", "List staged auto-skill proposals"),
    ("/skills quality", "Pending skill quality scores (1–100)"),
    ("/skills curator", "Show unused-skill prune status"),
    ("/learn", "Turn a source into a skill draft: /learn <hint|url|path>"),
    ("/launch", "External CLIs: manager / launch in tmux"),
    ("/launch list", "List CLI → sub-agent assignments"),
    ("/launch sessions", "List active tmux CLI sessions"),
    ("/launch claude", "Start Claude Code in tmux (Linux/macOS)"),
    ("/launch claude restart", "Restart Claude Code session"),
    ("/launch send", "Send prompt to running CLI session"),
    ("/cron", "Cron jobs: list rules (TUI manager)"),
    ("/cron list", "List scheduled cron jobs"),
    ("/cron add", "Add job: /cron add schedule :: task"),
    ("/cron enable", "Enable cron job by id"),
    ("/cron disable", "Disable cron job by id"),
    ("/cron remove", "Delete cron job by id"),
    ("/cron bind", "Post cron summaries to current session"),
    ("/spec", "SDD: status of openspec specs & changes"),
    ("/spec init", "Initialize openspec/ in workspace"),
    ("/spec create", "Scaffold change: /spec create <id> [project] [-- request]"),
    ("/spec propose", "Alias of /spec create"),
    ("/spec show", "View change status + proposal/tasks: /spec show <id>"),
    ("/spec view", "Alias of /spec show"),
    ("/spec fill", "Ask agent to fill stubs: /spec fill <id>"),
    ("/spec status", "SDD status or /spec status <change-id>"),
    ("/spec mode", "Set apply mode: /spec mode <id> self|subagents|hybrid"),
    ("/spec apply", "Run change: /spec apply <id>"),
    ("/spec run", "Alias of /spec apply"),
    ("/spec archive", "Archive change: /spec archive <id>"),
    ("/subagents", "List running sub-agents"),
    ("/subagent-types", "Manage custom sub-agent types (TUI)"),
    ("/subagent-types list", "List built-in and custom sub-agent types"),
    ("/subagent-spawn", "Spawn sub-agent: /subagent-spawn <type> <task>"),
    ("/subagent-result", "Sub-agent result by job id"),
    ("/subagent-terminate", "Stop a sub-agent by job id"),
    ("/lang", "Switch interface language (en / ru)"),
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
