"""CLI-side AgentEvent handlers (Rich console)."""

from __future__ import annotations

from core.agent_events import (
    AgentEvent,
    AssistantDeltaEvent,
    EventHandler,
    FinalResponseEvent,
    MaxStepsReachedEvent,
    SelfImprovementStartedEvent,
    SkillCreatedEvent,
    SkillProposedEvent,
    ThinkingEvent,
    ToolCallErrorEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
    create_compatibility_print_handler,
)


def create_rich_cli_handler() -> EventHandler:
    """Rich-colored handler for ``holix chat`` / ``holix run``."""
    try:
        from cli.utils.rich_console import (
            console,
            print_info,
            print_success,
            print_tool_call,
        )
    except ImportError:
        return create_compatibility_print_handler()

    def handler(event: AgentEvent) -> None:
        if isinstance(event, ToolCallStartEvent):
            print_tool_call(event.tool_name, status="running")
        elif isinstance(event, ToolCallResultEvent):
            print_tool_call(event.tool_name, status="done")
        elif isinstance(event, ToolCallErrorEvent):
            print_tool_call(event.tool_name, status="error")
        elif isinstance(event, SelfImprovementStartedEvent):
            print_info("Analyzing session for new skill creation...")
        elif isinstance(event, SkillCreatedEvent):
            print_success(f"New skill learned: {event.skill_name}")
        elif isinstance(event, SkillProposedEvent):
            print_info(
                f"Skill proposed for review: {event.skill_name} "
                f"({event.action}) — holix skills pending"
            )
        elif isinstance(event, ThinkingEvent):
            if "thinking" in event.message.lower():
                console.print(f"[dim]{event.message}[/dim]")
            else:
                print_info(event.message)
        elif isinstance(event, AssistantDeltaEvent):
            pass
        elif isinstance(event, FinalResponseEvent):
            pass
        elif isinstance(event, MaxStepsReachedEvent):
            console.print(f"[yellow]Agent reached maximum steps ({event.max_steps}).[/yellow]")

    return handler
