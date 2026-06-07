"""TUI slash command handling."""

from __future__ import annotations

from rich.panel import Panel
from textual.widgets import RichLog

from core.security.confirmation import ConfirmationChoice


class SlashCommandHandler:
    """Dispatches /commands to HelixApp actions."""

    def __init__(self, app) -> None:
        self.app = app

    async def handle(self, command: str) -> None:
        """Handle local TUI slash commands."""
        try:
            chat_log = self.app.query_one("#chat-log", RichLog)
            cmd = command.lower().strip()

            if cmd in ("/clear", "/cls"):
                self.app.action_clear_chat()

            elif cmd in ("/help", "/h", "/?"):
                self.app.action_help()

            elif cmd == "/metrics":
                try:
                    from core.monitoring.metrics import metrics
                    summary = metrics.get_summary()

                    lines = [
                        f"Requests: {summary.get('total_requests', 0)}",
                        f"Tool calls: {summary.get('total_tool_calls', 0)}",
                        f"Skills created: {summary.get('skills_created', 0)}",
                        f"Errors: {summary.get('total_errors', 0)}",
                    ]
                    if "avg_response_time" in summary:
                        lines.append(f"Avg response time: {summary['avg_response_time']:.2f}s")

                    self.app._append_to_log(Panel("\n".join(lines), title="Metrics", border_style="magenta"))
                except Exception as e:
                    self.app._append_to_log(f"[red]Failed to get metrics: {e}[/red]")

            elif cmd.startswith("/stream"):
                parts = cmd.split()
                if len(parts) > 1:
                    val = parts[1]
                    self.app.streaming_enabled = val in ("on", "true", "1")
                else:
                    self.app.streaming_enabled = not self.app.streaming_enabled

                status = "ON" if self.app.streaming_enabled else "OFF"
                self.app._append_to_log(f"[cyan]Streaming mode: {status}[/cyan]")

                self.app._update_sidebar()  # refresh model line with (stream) indicator

            elif cmd in ("/last", "/last-tool") or cmd.startswith("/last "):
                # /last or /last 2 (1-based from end, 0 or omitted = most recent)
                parts = cmd.split()
                idx = 0
                if len(parts) > 1:
                    try:
                        idx = max(0, int(parts[1]) - 1)  # user sees 1 = last, 2 = second last
                    except ValueError:
                        idx = 0
                self.app._show_full_tool_result(idx)

            elif cmd in ("/tools", "/tool-results", "/tool"):
                self.app._list_recent_tools()

            elif cmd in ("/regenerate", "/regen"):
                self.app.action_regenerate_last_response()

            elif cmd in ("/session-info", "/status", "/info"):
                self.app.action_show_session_info()

            elif cmd in ("/insert-assistant", "/insert-last-assistant"):
                self.app.action_insert_last_assistant()

            elif cmd in ("/insert-tool", "/insert-last-tool"):
                self.app._insert_last_tool_result_as_context()

            elif cmd in ("/edit-last", "/edit"):
                self.app.action_edit_last_message()

            elif cmd == "/compress":
                from cli.shared.commands.context_compress import run_context_compress

                await run_context_compress(self.app)

            elif cmd == "/init":
                from cli.shared.commands.project_init import run_project_init

                await run_project_init(self.app)

            elif cmd in ("/models", "/model"):
                try:
                    from cli.tui.modals.model_picker import open_model_picker

                    open_model_picker(self.app)
                except Exception as e:
                    self.app._append_to_log(f"[red]Models: {e}[/red]")

            elif cmd.startswith("/mode"):
                # /mode — cycle or set execution mode
                # /mode          → cycle to next mode (same as Shift+Tab)
                # /mode react    → set specific mode
                parts = command.split(maxsplit=1)
                mode_arg = parts[1].strip() if len(parts) > 1 else None
                if mode_arg:
                    valid_modes = {"react", "plan_and_execute", "hybrid", "auto"}
                    if mode_arg in valid_modes:
                        self.app._execution_mode_index = self.app._execution_modes.index(mode_arg)
                        await self.app.action_cycle_execution_mode(just_set=True)
                    else:
                        self.app._append_to_log(f"[red]Invalid mode: {mode_arg}[/red]")
                        self.app._append_to_log(f"[dim]Valid modes: {', '.join(self.app._execution_modes)}[/dim]")
                else:
                    await self.app.action_cycle_execution_mode()

            elif cmd.startswith("/subagent-spawn"):
                # /subagent-spawn <type> — spawn a sub-agent
                # Task comes from the input field
                parts = command.split(maxsplit=1)
                agent_type = parts[1].strip() if len(parts) > 1 else ""
                valid_types = {"researcher", "coder", "analyst", "reviewer", "writer"}
                if agent_type in valid_types:
                    self.app.run_worker(self.app._action_spawn_subagent(agent_type))
                else:
                    self.app._append_to_log("[yellow]Usage: /subagent-spawn <type>[/yellow]")
                    self.app._append_to_log(f"[dim]Valid types: {', '.join(sorted(valid_types))}[/dim]")

            elif cmd.startswith("/subagent-list") or cmd.startswith("/subagents"):
                self.app.run_worker(self.app._action_list_subagents())

            elif cmd.startswith("/subagent-terminate"):
                parts = command.split(maxsplit=1)
                name = parts[1].strip() if len(parts) > 1 else ""
                if name:
                    self.app.run_worker(self.app._action_terminate_subagent(name))
                else:
                    self.app._append_to_log("[yellow]Usage: /subagent-terminate <name>[/yellow]")

            elif cmd.startswith("/subagent-result"):
                parts = command.split(maxsplit=1)
                name = parts[1].strip() if len(parts) > 1 else ""
                if name:
                    self.app.run_worker(self.app._action_show_subagent_result(name))
                else:
                    self.app._append_to_log("[yellow]Usage: /subagent-result <name>[/yellow]")

            elif cmd.startswith("/ltm-stats"):
                self.app.run_worker(self.app._action_show_ltm_stats())

            elif cmd in ("/1", "/allow-once"):
                self.app._resolve_confirmation(ConfirmationChoice.ALLOW_ONCE)

            elif cmd in ("/2", "/allow-session"):
                self.app._resolve_confirmation(ConfirmationChoice.ALLOW_SESSION)

            elif cmd in ("/3", "/allow-always"):
                self.app._resolve_confirmation(ConfirmationChoice.ALLOW_ALWAYS)

            elif cmd in ("/4", "/deny"):
                self.app._resolve_confirmation(ConfirmationChoice.DENY)

            elif cmd.startswith("/safety permissions") or cmd == "/safety":
                self.app._show_safety_permissions()

            elif cmd == "/plan-confirm":
                from core.plan_review.review_guard import PlanReviewChoice
                self.app._resolve_plan_review(PlanReviewChoice.CONFIRM_STEP)

            elif cmd == "/plan-auto":
                from core.plan_review.review_guard import PlanReviewChoice
                self.app._resolve_plan_review(PlanReviewChoice.AUTO_EXECUTE)

            elif cmd == "/plan-refine":
                from core.plan_review.review_guard import PlanReviewChoice
                self.app._resolve_plan_review(PlanReviewChoice.REFINE)

            elif cmd == "/plan-reject":
                from core.plan_review.review_guard import PlanReviewChoice
                self.app._resolve_plan_review(PlanReviewChoice.REJECT)

            elif cmd in ("/stop", "/cancel", "/abort"):
                self.app._action_stop_all()

            elif cmd.startswith("/memory"):
                # /memory <query> — semantic search (results go to chat + Memory sidebar list)
                # /memory-clear — explicit clear of search results
                if cmd == "/memory-clear" or cmd.startswith("/memory-clear "):
                    self.app._clear_memory_search()
                    self.app._append_to_log("[dim]Memory sidebar reset to recent messages.[/dim]")
                else:
                    parts = command.split(maxsplit=1)
                    query = parts[1] if len(parts) > 1 else ""
                    if not query.strip() and self.app._memory_search_active:
                        # Empty /memory while in search → convenient clear
                        self.app._clear_memory_search()
                        self.app._append_to_log("[dim]Memory sidebar reset to recent messages.[/dim]")
                    else:
                        self.app.run_worker(self.app._search_memory_in_chat(query))

            elif cmd.startswith("/profile"):
                parts = cmd.split(maxsplit=1)
                if len(parts) > 1:
                    target = parts[1].strip()
                    profiles = self.app._get_available_profiles()

                    # Support switching by number
                    if target.isdigit():
                        idx = int(target) - 1
                        if 0 <= idx < len(profiles):
                            self.app.run_worker(self.app._switch_profile(profiles[idx]))
                        else:
                            self.app._append_to_log(f"[red]Invalid profile number: {target}[/red]")
                    else:
                        if target in profiles:
                            self.app.run_worker(self.app._switch_profile(target))
                        else:
                            self.app._append_to_log(f"[red]Profile '{target}' not found.[/red]")
                else:
                    self.app.run_worker(self.app._show_profile_switcher())

            elif cmd in ("/yes", "/confirm"):
                if self.app._pending_profile_switch:
                    target = self.app._pending_profile_switch
                    self.app._pending_profile_switch = None
                    self.app.run_worker(self.app._switch_profile(target))
                else:
                    self.app._append_to_log("[yellow]No pending profile switch.[/yellow]")

            elif cmd in ("/no", "/cancel"):
                if self.app._pending_profile_switch:
                    self.app._append_to_log(f"[dim]Cancelled switch to '{self.app._pending_profile_switch}'.[/dim]")
                    self.app._pending_profile_switch = None
                else:
                    self.app._append_to_log("[yellow]No pending profile switch.[/yellow]")

            elif cmd in ("/rerun", "/rerun last", "/repeat"):
                self.app.run_worker(self.app._rerun_last_tool())

            elif cmd in ("/copy", "/copy last"):
                self.app.action_copy_last_output()

            elif cmd.startswith("/density"):
                parts = cmd.split()
                level = parts[1] if len(parts) > 1 else "normal"
                if level in ("compact", "normal", "comfort"):
                    self.app.apply_density(level)
                    self.app._append_to_log(f"[dim]Density set to {level}.[/dim]")
                else:
                    self.app._append_to_log("[yellow]Usage: /density compact|normal|comfort[/yellow]")

            elif cmd == "/reset-ui":
                self.app._reset_ui_state()

            elif cmd.startswith("/session name ") or cmd.startswith("/name "):
                # /session name My Project Context
                parts = command.split(maxsplit=2)
                if len(parts) >= 3:
                    new_name = parts[2].strip()
                    self.app._rename_current_session(new_name)
                else:
                    self.app._append_to_log("[yellow]Usage: /session name <your session name>[/yellow]")

            elif cmd == "/copy log":
                self.app.action_copy_log()

            elif cmd in ("/new", "/newsession", "/session new"):
                self.app.run_worker(self.app._create_new_session())

            elif cmd in ("/sessions", "/history", "/s"):
                self.app.run_worker(self.app._show_sessions_list())

            elif cmd == "/skills" or cmd.startswith("/skills "):
                from cli.shared.commands.skills_commands import run_skills_command

                await run_skills_command(self.app, command)

            elif cmd.startswith("/switch ") or cmd.startswith("/s "):
                parts = cmd.split()
                if len(parts) > 1:
                    try:
                        idx = int(parts[1])
                        self.app.run_worker(self.app._switch_to_session(idx))
                    except ValueError:
                        self.app._append_to_log("[yellow]Usage: /switch 2  (number from /sessions)[/yellow]")
                else:
                    self.app._append_to_log("[yellow]Usage: /switch <number>[/yellow]")

            else:
                self.app._append_to_log(f"[yellow]Unknown command:[/yellow] {command}")
                self.app._append_to_log("[dim]See /help or use Ctrl+P (recommended) for full list of commands and actions[/dim]")

        except Exception:
            # Slash command failed — never kill the TUI because of a bad command
            try:
                chat_log = self.app.query_one("#chat-log", RichLog)
                self.app._append_to_log(f"[red]Command failed:[/red] {command}")
            except Exception:
                pass
