"""Slash command registry (shared by TUI and Telegram)."""

from __future__ import annotations

from pathlib import Path

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show help"),
    ("/status", "Profile, mode, session status"),
    ("/clear", "Clear transcript"),
    ("/metrics", "Show metrics"),
    ("/compress", "Compress conversation context (free context window)"),
    ("/init", "Deep project analysis → .helix/HELIX.md"),
    ("/stream", "Toggle streaming"),
    ("/mode", "Cycle execution mode"),
    ("/models", "Switch LLM model (runtime)"),
    ("/model", "Switch LLM model (alias)"),
    ("/stop", "Stop running tasks"),
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
    ("/skills", "Skills: helix skills list --agent <role>"),
    ("/cron", "Cron jobs: list rules (TUI manager)"),
    ("/cron list", "List scheduled cron jobs"),
    ("/cron add", "Add job: /cron add schedule :: task"),
    ("/cron enable", "Enable cron job by id"),
    ("/cron disable", "Disable cron job by id"),
    ("/cron remove", "Delete cron job by id"),
    ("/cron bind", "Post cron summaries to current session"),
    ("/subagents", "List running sub-agents"),
    ("/subagent-spawn", "Spawn sub-agent: /subagent-spawn <type> <task>"),
    ("/subagent-result", "Sub-agent result by job id"),
    ("/subagent-terminate", "Stop a sub-agent by job id"),
]


def all_slash_commands(
    skills_dir: Path | None = None,
    *,
    agent_slot: str = "main",
    skill_assignments: dict | None = None,
) -> list[tuple[str, str]]:
    """Static commands plus dynamic hub skill slash commands."""
    out = list(SLASH_COMMANDS)
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
    return out