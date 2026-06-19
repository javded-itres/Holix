"""Shared slash commands for TUI, Telegram, and other hosts."""

from __future__ import annotations

import asyncio
from typing import Any

from core.i18n import host_locale, set_host_locale, t
from core.plan_review.review_guard import PlanReviewChoice
from core.security.confirmation import ConfirmationChoice

from cli.shared.commands.registry import SLASH_COMMANDS
from cli.shared.slash_input import is_mode_slash, is_models_slash, normalize_slash_input


class AgentCommands:
    """Route /commands through an AgentHost implementation."""

    SLASH_COMMANDS = SLASH_COMMANDS

    def __init__(self, host: Any) -> None:
        self.host = host

    async def handle(self, command: str) -> None:
        cmd = normalize_slash_input(command.strip())
        lower = cmd.lower()
        h = self.host
        lang = host_locale(h)

        try:
            if lower.startswith("/lang"):
                await self._lang(cmd, lang)
                return

            if lower in ("/clear", "/cls"):
                h.action_clear_chat()

            elif lower in ("/help", "/h", "/?"):
                h.action_help()

            elif lower == "/status":
                await self._status(h)

            elif lower == "/metrics":
                await self._metrics()

            elif lower == "/compress":
                from cli.shared.commands.context_compress import run_context_compress

                await run_context_compress(h)

            elif lower == "/init":
                from cli.shared.commands.project_init import run_project_init

                await run_project_init(h)

            elif lower.startswith("/stream"):
                parts = lower.split()
                if len(parts) > 1:
                    h.streaming_enabled = parts[1] in ("on", "true", "1")
                else:
                    h.streaming_enabled = not h.streaming_enabled
                st = "on" if h.streaming_enabled else "off"
                h.transcript_write(f"[dim]{t('streaming', lang, state=st)}[/dim]")
                h._refresh_status_bar()

            elif is_models_slash(cmd):
                if hasattr(h, "push_screen"):
                    try:
                        from cli.tui.modals.model_picker import open_model_picker

                        open_model_picker(h)
                    except Exception as e:
                        h.transcript_write(f"[red]Models: {e}[/red]")
                elif hasattr(h, "_interactive"):
                    await h._interactive.show_models()
                else:
                    h.transcript_write(t("models_hint", lang))

            elif is_mode_slash(cmd):
                parts = lower.split()
                if len(parts) > 1 and parts[1] in h._execution_modes:
                    h._execution_mode_index = h._execution_modes.index(parts[1])
                    h.transcript_write(f"[dim]{t('mode_set', lang, mode=parts[1])}[/dim]")
                else:
                    await h.action_cycle_execution_mode()
                h._refresh_status_bar()

            elif lower == "/stop":
                h._action_stop_all()

            elif lower in ("/process-stop", "/process stop"):
                if hasattr(h, "_stop_background_process"):
                    h.run_worker(h._stop_background_process())
                else:
                    h.transcript_write("[yellow]/process-stop — TUI only[/yellow]")

            elif lower in ("/process", "/process list"):
                if hasattr(h, "_list_background_processes"):
                    h.run_worker(h._list_background_processes())
                else:
                    h.transcript_write("[yellow]/process — TUI only[/yellow]")

            elif lower == "/new":
                h.run_worker(h._create_new_session())

            elif lower == "/sessions":
                h.run_worker(h._show_sessions_list())

            elif lower.startswith("/switch"):
                parts = cmd.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    h.run_worker(h._switch_to_session(int(parts[1])))
                else:
                    h.transcript_write(f"[yellow]{t('usage_switch', lang)}[/yellow]")

            elif lower.startswith("/session name"):
                parts = cmd.split(maxsplit=2)
                if len(parts) >= 3:
                    h._rename_current_session(parts[2].strip())
                else:
                    h.transcript_write(f"[yellow]{t('usage_session_name', lang)}[/yellow]")

            elif lower.startswith("/profile"):
                await self._profile(cmd)

            elif lower.startswith("/memory-clear") or lower == "/memory clear":
                h._memory_search_query = ""
                h._memory_search_results = []
                h.transcript_write(f"[dim]{t('memory_cleared', lang)}[/dim]")

            elif lower.startswith("/memory"):
                query = cmd[7:].strip() if len(cmd) > 7 else ""
                if query:
                    h.run_worker(h._search_memory(query))
                else:
                    h.transcript_write(f"[yellow]{t('usage_memory', lang)}[/yellow]")

            elif lower in ("/last", "/last-tool"):
                h._show_full_tool_result(0)

            elif lower.startswith("/last "):
                idx = int(lower.split()[1]) if lower.split()[1].isdigit() else 0
                h._show_full_tool_result(idx)

            elif lower == "/tools":
                h._list_recent_tools()

            elif lower in ("/copy", "/copy last"):
                h.action_copy_output()

            elif lower in ("/copy tool", "/copy-tool"):
                text = h._transcript_store.last_tool()
                if not text and h._recent_tool_results:
                    text = h._recent_tool_results[-1]["full_result"]
                h.copy_text(text or "", label=t("copy_tool", lang))

            elif lower in ("/copy all", "/copy-all", "/copy log"):
                body = h._transcript_store.format_all()
                h.copy_text(body, label=t("copy_all", lang))

            elif lower in ("/open", "/view", "/transcript"):
                h.action_open_transcript()

            elif lower in ("/yes", "/1"):
                h._resolve_confirmation(ConfirmationChoice.ALLOW_ONCE)

            elif lower == "/2":
                h._resolve_confirmation(ConfirmationChoice.ALLOW_SESSION)

            elif lower == "/3":
                h._resolve_confirmation(ConfirmationChoice.ALLOW_ALWAYS)

            elif lower in ("/no", "/4"):
                h._resolve_confirmation(ConfirmationChoice.DENY)

            elif lower == "/plan-confirm":
                h._resolve_plan_review(PlanReviewChoice.CONFIRM_STEP)

            elif lower == "/plan-auto":
                h._resolve_plan_review(PlanReviewChoice.AUTO_EXECUTE)

            elif lower == "/plan-refine":
                h._resolve_plan_review(PlanReviewChoice.REFINE)

            elif lower == "/plan-reject":
                h._resolve_plan_review(PlanReviewChoice.REJECT)

            elif lower.startswith("/mcp"):
                await self._mcp(cmd)

            elif lower.startswith("/launch"):
                from cli.shared.commands.launch_commands import run_launch_command

                await run_launch_command(h, cmd)

            elif lower.startswith("/cron"):
                from cli.shared.commands.cron_commands import run_cron_command

                await run_cron_command(h, cmd)

            elif lower.startswith("/hub") or lower in ("/plugins", "/marketplace"):
                await self._hub(cmd)

            elif lower == "/skills" or lower.startswith("/skills "):
                from cli.shared.commands.skills_commands import run_skills_command

                await run_skills_command(h, cmd)

            elif lower == "/skill" or lower.startswith("/skill "):
                from cli.shared.commands.skills_commands import run_skill_invoke_command

                await run_skill_invoke_command(h, cmd)

            elif lower.startswith("/subagent-types"):
                from cli.shared.commands.subagent_types_commands import (
                    run_subagent_types_command,
                )

                await run_subagent_types_command(h, cmd)

            elif lower.startswith("/subagent") or lower == "/subagents":
                from cli.shared.commands.subagent_commands import run_subagents_command

                await run_subagents_command(h, cmd)

            elif lower.startswith("/search"):
                from cli.shared.commands.search_commands import run_search_command

                await run_search_command(h, cmd)

            elif await self._try_skill_slash(h, cmd):
                pass

            else:
                h.transcript_write(f"[yellow]{t('unknown_cmd', lang, cmd=cmd)}[/yellow]")
                h.transcript_write(f"[dim]{t('type_help', lang)}[/dim]")

        except Exception as e:
            h.transcript_write(f"[red]{t('command_failed', lang, error=e)}[/red]")

    async def _status(self, h: Any) -> None:
        if hasattr(h, "action_status"):
            result = h.action_status()
            if asyncio.iscoroutine(result):
                await result
            return
        lang = host_locale(h)
        mode = h._execution_modes[h._execution_mode_index]
        h.transcript_write(
            f"[dim]{t('status_line', lang, profile=h.profile, mode=mode, session=h.conversation_id)}[/dim]"
        )

    async def _metrics(self) -> None:
        h = self.host
        try:
            from core.monitoring.metrics import format_metrics_message, metrics

            h.transcript_write(format_metrics_message(metrics.get_summary()))
        except Exception as e:
            h.transcript_write(t("metrics_error", host_locale(h), error=e))

    async def _lang(self, command: str, lang: str) -> None:
        h = self.host
        parts = command.split()
        if len(parts) == 1:
            h.transcript_write(t("lang.current", lang, code=lang.upper()))
            h.transcript_write(t("lang.usage", lang))
            return
        target = parts[1].strip().lower()
        try:
            new_lang = set_host_locale(h, target)
        except ValueError:
            h.transcript_write(t("lang.invalid", lang, value=parts[1]))
            return
        h.transcript_write(t("lang.set", new_lang, code=new_lang.upper()))
        if hasattr(h, "_refresh_status_bar"):
            h._refresh_status_bar()
        if hasattr(h, "_sync_telegram_menu"):
            await h._sync_telegram_menu()

    async def _profile(self, command: str) -> None:
        from core.profile_keys import profile_has_access_key

        from cli.core import ProfileManager

        h = self.host
        lang = host_locale(h)
        parts = command.split()
        profiles = h._get_available_profiles()
        manager = ProfileManager()
        hidden_list = self._telegram_profile_list_hidden(h)
        if len(parts) >= 2:
            target = parts[1]
            profile_key = parts[2] if len(parts) >= 3 else None
            if profile_key:
                if manager.profile_exists(target):
                    h.run_worker(h._switch_profile(target, profile_key=profile_key))
                else:
                    h.transcript_write(f"[red]{t('unknown_profile', lang, name=target)}[/red]")
            elif target.isdigit() and profile_key is None:
                idx = int(target) - 1
                if 0 <= idx < len(profiles):
                    h.run_worker(h._switch_profile(profiles[idx]))
                else:
                    h.transcript_write(f"[red]{t('invalid_profile_num', lang)}[/red]")
            elif target in profiles:
                h.run_worker(h._switch_profile(target, profile_key=profile_key))
            elif hidden_list and manager.profile_exists(target):
                h.transcript_write(
                    f"[yellow]{t('tg.profile_requires_key', lang, name=target)}[/yellow]"
                )
            else:
                h.transcript_write(f"[red]{t('unknown_profile', lang, name=target)}[/red]")
        else:
            lines = [f"[bold]{t('profiles_title', lang)}[/bold]"]
            if hidden_list:
                mark = " *" if h.profile else ""
                lines.append(f"  {h.profile}{mark}")
                lines.append(f"[dim]{t('tg.profile_switch_by_key', lang)}[/dim]")
            else:
                for i, p in enumerate(profiles, 1):
                    mark = " *" if p == h.profile else ""
                    lock = " [dim](locked)[/dim]" if profile_has_access_key(p) else ""
                    lines.append(f"  {i}. {p}{mark}{lock}")
                lines.append(f"[dim]{t('usage_profile', lang)}[/dim]")
                lines.append("[dim]/profile <name> <access-key>[/dim]")
            h.transcript_write("\n".join(lines))

    @staticmethod
    def _telegram_profile_list_hidden(host: Any) -> bool:
        session = getattr(host, "_session", None)
        if session is None:
            return False
        from integrations.telegram.profile_visibility import is_profile_list_hidden

        bot_profile = getattr(session, "bot_profile", "default")
        user_id = getattr(session, "user_id", None)
        if user_id is None:
            return False
        return is_profile_list_hidden(bot_profile, int(user_id))

    async def _try_skill_slash(self, h: Any, command: str) -> bool:
        """Legacy: run a skill via /skill-name [args] (prefer /skill <name>)."""
        from core.hub.slash_registry import load_skill_slash_commands

        config = getattr(h, "config", None)
        if not config or not getattr(config, "skills_dir", None):
            return False

        parts = command.strip().split(maxsplit=1)
        cmd_token = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        skill_name = cmd_token.lstrip("/")

        agent_slot = getattr(h, "agent_slot", None) or getattr(
            getattr(h, "agent", None), "agent_slot", "main"
        )
        assignments = getattr(config, "skill_assignments", None) or {}

        from pathlib import Path

        registered = {
            c.lower()
            for c, _ in load_skill_slash_commands(
                Path(config.skills_dir),
                agent_slot=agent_slot,
                skill_assignments=assignments,
            )
        }
        if cmd_token not in registered:
            return False

        from cli.shared.commands.skills_commands import invoke_skill_by_name

        return await invoke_skill_by_name(h, skill_name, args)

    async def _hub(self, command: str) -> None:
        """Skill hub: pick catalog in TUI or open a specific source."""
        h = self.host
        cmd = command.strip()
        lower = cmd.lower()
        parts = lower.split()
        profile = getattr(h, "profile", "default")
        config = getattr(h, "config", None)

        from core.hub.catalog import resolve_hub_source

        highlight: str | None = None
        if lower in ("/plugins", "/marketplace"):
            highlight = "claude-official"
        elif len(parts) > 1:
            highlight = resolve_hub_source(parts[1])

        if config and hasattr(h, "push_screen"):
            from cli.tui.modals.hub_browser import open_hub_browser, open_hub_pick

            if len(parts) > 1 and parts[1] in ("installed", "list"):
                open_hub_browser(h, profile, config, initial_mode="installed")
            elif highlight and (len(parts) > 1 and parts[1] not in ("browse", "install", "menu")):
                open_hub_browser(h, profile, config, default_source=highlight)
            else:
                open_hub_pick(h, profile, config, highlight_source=highlight)
            return

        lines = [
            "[bold]Skill Hub[/bold]",
            "  [cyan]/hub[/cyan]  — pick catalog (TUI)",
            "  [cyan]/hub installed[/cyan]  — hub skills, plugins, MCP (TUI)",
            "  [cyan]/hub clawhub[/cyan]  ·  [cyan]/hub hermes[/cyan]  ·  [cyan]/hub claude[/cyan]",
            "  [cyan]holix hub browse[/cyan]  ·  [cyan]holix hub list[/cyan]",
        ]
        if config and getattr(config, "skills_dir", None):
            try:
                from pathlib import Path

                from core.hub import SkillImporter

                entries = SkillImporter(Path(config.skills_dir)).lock.list_entries()
                if entries:
                    lines.append("[dim]Installed via hub:[/dim]")
                    for e in entries[:8]:
                        ver = f"@{e.version}" if e.version else ""
                        lines.append(f"  · {e.skill_name} ({e.source}{ver})")
                    if len(entries) > 8:
                        lines.append(f"  … +{len(entries) - 8} more")
            except Exception:
                pass
        h.transcript_write("\n".join(lines))

    async def _mcp(self, command: str) -> None:
        """Handle /mcp family of commands. Delegates to host methods when available."""
        h = self.host
        cmd = command.strip()
        lower = cmd.lower()
        parts = lower.split()

        sub = parts[1] if len(parts) > 1 else ""

        # Try rich interactive first (Telegram has _interactive with mcp methods)
        if hasattr(h, "_interactive") and hasattr(h._interactive, "show_mcp_menu"):
            if sub in ("", "menu", "list"):
                await h._interactive.show_mcp_menu()
                return
            # for others, fall through to host methods or simple

        # Simple transcript-based or direct host method calls
        if sub in ("", "list"):
            if hasattr(h, "_mcp_list"):
                h.run_worker(h._mcp_list())
            else:
                # Fallback: try to read from current config
                try:
                    from cli.core import get_current_config
                    cfg = get_current_config()
                    servers = getattr(cfg, "mcp_servers", {}) or {}
                    if not servers:
                        h.transcript_write("No MCP servers configured. Use CLI: holix mcp install")
                    else:
                        lines = ["MCP servers:"]
                        for name, data in servers.items():
                            src = data.get("_source", "manual")
                            lines.append(f"  • {name} ({data.get('transport','stdio')}) [{src}]")
                        h.transcript_write("\n".join(lines))
                except Exception as e:
                    h.transcript_write(f"MCP list error: {e}")
            return

        if sub == "tools":
            if hasattr(h, "_mcp_list_tools"):
                h.run_worker(h._mcp_list_tools())
            else:
                # List tools from registry that look like mcp_
                try:
                    agent = getattr(h, "agent", None) or getattr(h, "_session", None) and getattr(h._session, "agent", None)
                    if agent and hasattr(agent, "tools"):
                        mcp_tools = [n for n in agent.tools.get_tool_names() if n.startswith("mcp_")]
                        if mcp_tools:
                            h.transcript_write("MCP tools available:\n" + "\n".join(f"  • {t}" for t in mcp_tools))
                        else:
                            h.transcript_write("No MCP tools currently registered (assign servers first).")
                    else:
                        h.transcript_write("Agent/tools not ready.")
                except Exception as e:
                    h.transcript_write(f"Error listing MCP tools: {e}")
            return

        if sub in ("install", "add"):
            arg = cmd.split(maxsplit=2)[2] if len(parts) > 2 else ""
            if hasattr(h, "_mcp_install"):
                h.run_worker(h._mcp_install(arg))
            else:
                h.transcript_write("Use CLI for install: holix mcp install [name|git-url]")
                h.transcript_write("Example: holix mcp install compass  (or context7, filesystem, etc.)")
            return

        if sub in ("assign", "enable"):
            # /mcp assign server role1,role2
            rest = cmd.split(maxsplit=2)[2] if len(parts) > 2 else ""
            if hasattr(h, "_mcp_assign"):
                h.run_worker(h._mcp_assign(rest))
            else:
                h.transcript_write("MCP assign via CLI: holix mcp assign")
            return

        if sub == "test":
            name = parts[2] if len(parts) > 2 else ""
            if hasattr(h, "_mcp_test"):
                h.run_worker(h._mcp_test(name))
            else:
                h.transcript_write("Test via CLI: holix mcp test <name>")
            return

        if sub in ("remove", "rm", "delete"):
            name = parts[2] if len(parts) > 2 else ""
            if hasattr(h, "_mcp_remove"):
                h.run_worker(h._mcp_remove(name))
            else:
                h.transcript_write("Remove via CLI: holix mcp remove <name>")
            return

        # Unknown subcommand
        h.transcript_write("MCP commands: /mcp, /mcp list, /mcp install <name|url>, /mcp assign, /mcp remove <name>, /mcp test <name>, /mcp tools")
        h.transcript_write("For full UI use Telegram menus or TUI, or run `holix mcp` in terminal.")