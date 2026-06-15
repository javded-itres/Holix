"""Interactive chat command for Holix CLI."""

from __future__ import annotations

import asyncio

# Import agent
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from cli.core import HOLIX_HOME, ProfileConfig, get_profile_manager, switch_profile
from cli.utils.banner import show_banner, show_welcome_message
from cli.utils.rich_console import (
    console,
    create_spinner,
    print_assistant_message,
    print_error,
    print_info,
    print_panel,
    print_success,
    print_table,
    print_tool_call,
    print_user_message,
)

sys.path.append(str(Path(__file__).parent.parent.parent))

if TYPE_CHECKING:
    from core.agent import HolixAgent

# Prompt style
prompt_style = Style.from_dict({
    'prompt': '#00d7ff bold',  # Cyan
})


class ChatSession:
    """Interactive chat session with Holix."""

    def __init__(self, profile: str, config: ProfileConfig):
        """Initialize chat session.

        Args:
            profile: Profile name
            config: Profile configuration
        """
        self.profile = profile
        self.config = config
        self.agent: HolixAgent | None = None
        self.conversation_id = f"cli_chat_{profile}"

        # Event history for the current session (for /debug events)
        self.event_history: list = []
        self.max_event_history = 100

        # Streaming mode toggle
        self.streaming_enabled: bool = False

        # Create prompt session with history
        history_file = HOLIX_HOME / "logs" / f"history_{profile}.txt"
        history_file.parent.mkdir(parents=True, exist_ok=True)

        self.session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            style=prompt_style
        )

    async def initialize_agent(self):
        """Initialize the Holix agent."""
        with console.status("[bold cyan]Initializing Holix...", spinner="dots"):
            from core.agent_events import (
                create_compatibility_print_handler,
                create_rich_cli_handler,
            )
            from core.di import resolve_runtime_config

            runtime_config = resolve_runtime_config(self.config)

            try:
                from core.models.manager import ModelManager

                model_config = ModelManager(self.config).get_default_model_config()
                if model_config:
                    runtime_config = runtime_config.with_overrides(
                        model=model_config.model,
                        base_url=model_config.base_url,
                        api_key=model_config.api_key,
                        temperature=model_config.temperature,
                    )
                    console.print(
                        f"[dim]Using provider: {model_config.provider}, model: {model_config.model}[/dim]"
                    )
            except Exception as e:
                console.print(
                    f"[dim yellow]Warning: Could not load provider config ({e}), using profile defaults[/dim yellow]"
                )

            try:
                listeners = [create_rich_cli_handler()]
            except Exception:
                listeners = [create_compatibility_print_handler()]

            from core.agent import HolixAgent

            self.agent = HolixAgent(
                config=runtime_config,
                event_listeners=listeners,
            )
            await self.agent.initialize()

            # Attach event history recorder (for /debug events)
            self._attach_event_history_recorder()

    def _attach_event_history_recorder(self):
        """Attach a handler that records all events for /debug events command."""
        from core.agent_events import AgentEvent

        def record_event(event: AgentEvent):
            self.event_history.append(event)
            # Keep only the last N events
            if len(self.event_history) > self.max_event_history:
                self.event_history = self.event_history[-self.max_event_history:]

        try:
            self.agent.events.subscribe(record_event)
        except Exception:
            pass  # Non-critical

    def _event_summary(self, event) -> str:
        """Create a short human-readable summary for an event."""
        from core.agent_events import (
            AssistantDeltaEvent,
            ErrorEvent,
            FinalResponseEvent,
            SkillCreatedEvent,
            ThinkingEvent,
            ToolCallResultEvent,
            ToolCallStartEvent,
        )

        if isinstance(event, ToolCallStartEvent):
            return f"→ {event.tool_name}"
        elif isinstance(event, ToolCallResultEvent):
            return f"✓ {event.tool_name} ({event.duration_ms:.0f}ms)" if event.duration_ms else f"✓ {event.tool_name}"
        elif isinstance(event, AssistantDeltaEvent):
            preview = event.content[:60].replace("\n", " ")
            return f"delta: {preview}..."
        elif isinstance(event, FinalResponseEvent):
            return f"final ({event.steps_taken} steps)"
        elif isinstance(event, ThinkingEvent):
            return event.message
        elif isinstance(event, ErrorEvent):
            return f"error: {event.error[:50]}"
        elif isinstance(event, SkillCreatedEvent):
            return f"new skill: {event.skill_name}"
        else:
            return str(event)[:80]

    async def handle_special_command(self, command: str) -> bool:
        """Handle special slash commands.

        Args:
            command: Command string

        Returns:
            True if command was handled, False otherwise
        """
        cmd_lower = command.lower().strip()

        if cmd_lower in ("/yes", "/1"):
            from core.security.confirmation import ConfirmationChoice
            from core.subagents.interaction import resolve_any_confirmation

            if self.agent and resolve_any_confirmation(self.agent, ConfirmationChoice.ALLOW_ONCE):
                print_success("Allowed once")
            else:
                print_info("No pending confirmation")
            return True

        if cmd_lower == "/2":
            from core.security.confirmation import ConfirmationChoice
            from core.subagents.interaction import resolve_any_confirmation

            if self.agent and resolve_any_confirmation(self.agent, ConfirmationChoice.ALLOW_SESSION):
                print_success("Allowed for this session")
            else:
                print_info("No pending confirmation")
            return True

        if cmd_lower == "/3":
            from core.security.confirmation import ConfirmationChoice
            from core.subagents.interaction import resolve_any_confirmation

            if self.agent and resolve_any_confirmation(self.agent, ConfirmationChoice.ALLOW_ALWAYS):
                print_success("Allowed always")
            else:
                print_info("No pending confirmation")
            return True

        if cmd_lower in ("/no", "/4"):
            from core.security.confirmation import ConfirmationChoice
            from core.subagents.interaction import resolve_any_confirmation

            if self.agent and resolve_any_confirmation(self.agent, ConfirmationChoice.DENY):
                print_success("Denied")
            else:
                print_info("No pending confirmation")
            return True

        # /exit or /quit
        if cmd_lower in ["/exit", "/quit", "/q"]:
            print_info("Goodbye! 👋")
            return "exit"

        # /clear
        elif cmd_lower == "/clear":
            self.conversation_id = f"cli_chat_{self.profile}_{int(asyncio.get_event_loop().time())}"
            print_success("Conversation cleared")
            return True

        # /model
        elif cmd_lower.startswith("/model"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2:
                self.config.model = parts[1]
                print_success(f"Switched to model: {parts[1]}")
                print_info("Reinitializing agent...")
                await self.initialize_agent()
            else:
                print_info(f"Current model: {self.config.model}")
            return True

        # /profile
        elif cmd_lower.startswith("/profile"):
            from core.profile_keys import ProfileKeyError, profile_has_access_key

            parts = command.split(maxsplit=2)
            if len(parts) >= 2:
                new_profile = parts[1]
                profile_key = parts[2] if len(parts) == 3 else None
                manager = get_profile_manager()
                if manager.profile_exists(new_profile):
                    try:
                        self.config = switch_profile(new_profile, profile_key=profile_key)
                        self.profile = new_profile
                        self.conversation_id = f"cli_chat_{new_profile}"
                        print_success(f"Switched to profile: {new_profile}")
                        print_info("Reinitializing agent...")
                        await self.initialize_agent()
                    except ProfileKeyError as exc:
                        print_error(str(exc))
                        if profile_has_access_key(new_profile) and not profile_key:
                            print_info("Usage: /profile <name> <access-key>")
                else:
                    print_error(f"Profile '{new_profile}' does not exist")
            else:
                manager = get_profile_manager()
                profiles = manager.list_profiles()
                rows = [
                    [
                        p,
                        "locked" if profile_has_access_key(p) else "open",
                        "✓" if p == self.profile else "",
                    ]
                    for p in profiles
                ]
                print_table("Available Profiles", ["Profile", "Access", "Active"], rows)
                print_info("Switch: /profile <name> <access-key>")
            return True

        # /skills
        elif cmd_lower == "/skills":
            if self.agent:
                skills = self.agent.get_skills()
                if skills:
                    rows = [[name, s.get("description", "")[:50]] for name, s in list(skills.items())[:10]]
                    print_table(f"Active Skills ({len(skills)} total)", ["Skill", "Description"], rows)
                else:
                    print_info("No skills available yet")
            return True

        # /memory
        elif cmd_lower.startswith("/memory"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2 and self.agent:
                query = parts[1]
                with create_spinner() as progress:
                    task = progress.add_task("Searching memory...", total=None)
                    results = await self.agent.search_memory(query, top_k=5)
                    progress.remove_task(task)

                if results:
                    from core.memory.session_search import format_memory_hit_line

                    console.print("\n[cyan]Memory Search Results:[/cyan]\n")
                    for i, result in enumerate(results, 1):
                        console.print(format_memory_hit_line(result, index=i, content_limit=200))
                    console.print()
                else:
                    print_info("No results found")
            else:
                print_error("Usage: /memory <query>")
            return True

        # /help
        elif cmd_lower == "/help":
            show_welcome_message(console)
            return True

        # /status
        elif cmd_lower == "/status":
            console.print("\n[cyan]Current Status:[/cyan]")
            console.print(f"  Profile: {self.profile}")
            console.print(f"  Model: {self.config.model}")
            console.print(f"  Temperature: {self.config.temperature}")
            console.print(f"  Conversation ID: {self.conversation_id}")
            # Show context usage
            if self.agent and hasattr(self.agent, 'context_manager'):
                messages = await self.agent.memory.get_conversation(self.conversation_id, limit=200)
                usage = self.agent.context_manager.get_usage(messages)
                level = self.agent.context_manager.get_usage_level(messages)
                color_map = {"green": "green", "yellow": "yellow", "red": "red"}
                color = color_map.get(level, "white")
                ctx_display = self.agent.context_manager.format_usage_display(messages)
                console.print(f"  Context: [{color}]{ctx_display}[/{color}]")
                console.print(f"  Context Window: {usage['total']:,} tokens")
            console.print()
            return True

        # /metrics - show real-time metrics collected via AgentEvent system
        elif cmd_lower == "/metrics":
            try:
                from core.monitoring.metrics import metrics
                summary = metrics.get_summary()

                lines = [
                    f"[cyan]Total Requests:[/cyan] {summary.get('total_requests', 0)}",
                    f"[cyan]Tool Calls:[/cyan] {summary.get('total_tool_calls', 0)}",
                    f"[cyan]Skills Created:[/cyan] {summary.get('skills_created', 0)}",
                    f"[cyan]Errors:[/cyan] {summary.get('total_errors', 0)}",
                ]

                if 'avg_response_time' in summary:
                    lines.append(f"[cyan]Avg Response Time:[/cyan] {summary['avg_response_time']:.2f}s")

                print_panel("\n".join(lines), title="Holix Metrics (via Event System)", border_style="magenta")
            except Exception as e:
                print_error(f"Could not load metrics: {e}")
            return True

        # /debug events - show recent events from this session
        elif cmd_lower.startswith("/debug events"):
            parts = command.split(maxsplit=2)
            limit = 20
            if len(parts) > 2 and parts[2].isdigit():
                limit = int(parts[2])

            events_to_show = self.event_history[-limit:] if self.event_history else []

            if not events_to_show:
                print_info("No events recorded in this session yet.")
            else:
                console.print(f"\n[bold magenta]Recent Events ({len(events_to_show)} of {len(self.event_history)} total)[/bold magenta]\n")
                for i, ev in enumerate(events_to_show, 1):
                    ts = ev.timestamp.strftime("%H:%M:%S")
                    summary = self._event_summary(ev)
                    console.print(f"[dim]{i:2}.[/dim] [{ts}] {ev.type.value:<20} {summary}")

            console.print()
            return True

        # /debug - general debug help
        elif cmd_lower == "/debug":
            console.print("\n[bold]Debug commands:[/bold]")
            console.print("  /debug events [N]   - Show last N events from this session")
            console.print("  /stream [on|off]    - Toggle streaming mode")
            console.print("  /metrics            - Show agent metrics")
            console.print()
            return True

        # /stream - toggle or set streaming mode
        elif cmd_lower.startswith("/stream"):
            parts = command.split(maxsplit=1)
            arg = parts[1].strip().lower() if len(parts) > 1 else None

            if arg in ("on", "true", "1"):
                self.streaming_enabled = True
            elif arg in ("off", "false", "0"):
                self.streaming_enabled = False
            else:
                # toggle
                self.streaming_enabled = not self.streaming_enabled

            mode = "ON (real-time deltas)" if self.streaming_enabled else "OFF (full response)"
            print_success(f"Streaming mode: {mode}")
            if self.streaming_enabled:
                print_info("Responses will now stream token-by-token when supported.")
            return True

        elif cmd_lower == "/compress":
            from cli.shared.commands.context_compress import run_context_compress
            from cli.shared.rich_text import content_to_plain_text

            session = self

            class _ChatCompressHost:
                agent = session.agent
                conversation_id = session.conversation_id

                @staticmethod
                def transcript_write(content: object) -> None:
                    text = content_to_plain_text(content)
                    if not text:
                        return
                    low = text.lower()
                    if "error" in low or low.startswith("could not"):
                        print_error(text)
                    elif "compressed:" in low or "context compressed" in low:
                        print_success(text)
                    elif "not enough" in low or text.endswith("…"):
                        print_info(text)
                    else:
                        print_info(text)

            await run_context_compress(_ChatCompressHost())
            return True

        elif cmd_lower.startswith("/subagent"):
            from cli.shared.commands.subagent_commands import run_subagents_command
            from cli.shared.commands.subagent_types_commands import run_subagent_types_command
            from cli.shared.rich_text import content_to_plain_text

            session = self

            class _ChatSubagentHost:
                def __init__(self, chat_session: ChatSession) -> None:
                    self.agent = chat_session.agent
                    self.profile = chat_session.profile

                def transcript_write(self, content: object) -> None:
                    text = content_to_plain_text(content)
                    if not text:
                        return
                    low = text.lower()
                    if "failed" in low or low.startswith("unknown") or "disabled" in low:
                        print_error(text)
                    elif low.startswith("spawned"):
                        print_success(text)
                    else:
                        print_info(text)

            host = _ChatSubagentHost(session)
            if cmd_lower.startswith("/subagent-types"):
                await run_subagent_types_command(host, command)
            else:
                await run_subagents_command(host, command)
            return True

        return False

    async def chat_loop(self):
        """Main interactive chat loop."""
        show_banner(console, self.profile)
        show_welcome_message(console)

        # Initialize agent
        await self.initialize_agent()

        # Live status management for nice ThinkingEvent + tool progress display
        self._spinner_task = None
        self._progress = None

        def create_chat_event_handler():
            """Returns an event handler tailored for the interactive chat UX."""
            from core.agent_events import (
                FinalResponseEvent,
                ThinkingEvent,
                ToolCallResultEvent,
                ToolCallStartEvent,
            )
            from core.security.confirmation_events import ConfirmationRequestEvent
            from core.subagents.interaction_events import SubAgentQuestionEvent

            def handler(event):
                try:
                    if isinstance(event, ThinkingEvent):
                        status = event.message
                        if self._progress and self._spinner_task is not None:
                            self._progress.update(self._spinner_task, description=status)
                        else:
                            console.print(f"[dim]{status}[/dim]")

                    elif isinstance(event, ToolCallStartEvent):
                        status = f"Using tool: {event.tool_name}..."
                        if self._progress and self._spinner_task is not None:
                            self._progress.update(self._spinner_task, description=status)
                        else:
                            print_tool_call(event.tool_name, status="running")

                    elif isinstance(event, ToolCallResultEvent):
                        status = f"Tool completed: {event.tool_name}"
                        if self._progress and self._spinner_task is not None:
                            self._progress.update(self._spinner_task, description=status)
                        else:
                            print_tool_call(event.tool_name, status="done")

                    elif isinstance(event, FinalResponseEvent):
                        if self._progress and self._spinner_task is not None:
                            self._progress.update(self._spinner_task, description="Finalizing response...")

                    elif isinstance(event, SubAgentQuestionEvent):
                        name = event.subagent_name or "sub-agent"
                        q = (event.question or "").strip()
                        print_info(
                            f"❓ {name} asks: {q}\n"
                            f"Reply: /subagent-reply {name} …, @{name} …, "
                            "or plain text if only one question is pending"
                        )

                    elif isinstance(event, ConfirmationRequestEvent):
                        sub = f" (sub-agent {event.subagent_name})" if event.subagent_name else ""
                        print_info(
                            f"Confirmation required{sub}: {event.tool_name} — "
                            "/1 once, /2 session, /3 always, /4 deny"
                        )

                except Exception:
                    pass  # Never break the agent because of UI

            return handler

        # Attach a chat-specific rich handler that can drive the spinner
        chat_handler = create_chat_event_handler()
        # Re-attach (we may have the default rich one already)
        try:
            self.agent.events.subscribe(chat_handler)
        except Exception:
            pass

        # Main loop
        while True:
            try:
                # Get user input
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.session.prompt([
                        ('class:prompt', '❯ '),
                    ])
                )

                if not user_input.strip():
                    continue

                # Handle special commands
                if user_input.startswith('/'):
                    result = await self.handle_special_command(user_input)
                    if result == "exit":
                        break
                    continue

                if self.agent:
                    from core.subagents.interaction import try_route_subagent_reply

                    handled, feedback = try_route_subagent_reply(self.agent, user_input)
                    if handled:
                        print_user_message(user_input)
                        if feedback:
                            print_info(feedback)
                        continue

                # Print user message
                print_user_message(user_input)

                # Run agent with spinner whose description is updated live by events
                with create_spinner() as progress:
                    self._progress = progress
                    self._spinner_task = progress.add_task("Holix is thinking...", total=None)

                    try:
                        if self.streaming_enabled:
                            # Streaming path - use unified generator directly
                            from core.agent_events import AssistantDeltaEvent, FinalResponseEvent
                            from core.runtime.executor import run_holix

                            full_response = ""
                            async for event in run_holix(
                                self.agent,
                                user_input,
                                self.conversation_id,
                                stream=True,
                            ):
                                self.agent.emit(event)  # still feed other handlers

                                if isinstance(event, AssistantDeltaEvent):
                                    full_response += event.content
                                    # Print delta live (simple approach)
                                    console.print(event.content, end="", highlight=False)
                                elif isinstance(event, FinalResponseEvent):
                                    console.print()  # newline after streaming

                            response = full_response or "No response generated"
                        else:
                            # Classic non-streaming path
                            response = await self.agent.run(
                                user_input=user_input,
                                conversation_id=self.conversation_id
                            )
                    finally:
                        progress.remove_task(self._spinner_task)
                        self._spinner_task = None
                        self._progress = None

                # Print assistant response (for non-streaming or if needed)
                if not self.streaming_enabled:
                    print_assistant_message(response, markdown=True)

            except KeyboardInterrupt:
                console.print("\n")
                confirm = input("Exit chat? (y/n): ")
                if confirm.lower() == 'y':
                    print_info("Goodbye! 👋")
                    break
                console.print()
                continue

            except EOFError:
                print_info("\nGoodbye! 👋")
                break

            except Exception as e:
                print_error(f"Unexpected error: {e}")
                if self.config.__dict__.get("verbose"):
                    console.print_exception()


async def run_one_command(profile: str, config: ProfileConfig, command: str) -> bool:
    """Initialize agent and run a single slash command."""
    session = ChatSession(profile, config)
    await session.initialize_agent()
    if not command.strip().startswith("/"):
        command = f"/{command.lstrip('/')}"
    return await session.handle_special_command(command)


async def run_interactive_chat(profile: str, config: ProfileConfig):
    """Run interactive chat session.

    Args:
        profile: Profile name
        config: Profile configuration
    """
    session = ChatSession(profile, config)
    await session.chat_loop()
