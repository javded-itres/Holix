"""
SubAgent Management Widget for Holix TUI.

Provides a sidebar section for managing sub-agents:
- List active sub-agents with status
- Spawn predefined sub-agents
- Terminate running sub-agents
- View sub-agent results

Also includes memory stats display and execution mode selector.

This module is designed to be integrated into the main HolixTUI app
by adding the widget to the sidebar in compose() and connecting
the action methods.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Button, ListItem, ListView, Static, TextArea

# ─── Messages (posted when user interacts with the widget) ──────────────────

class SpawnSubAgent(Message):
    """User wants to spawn a sub-agent."""
    def __init__(self, agent_type: str, task: str) -> None:
        self.agent_type = agent_type
        self.task = task
        super().__init__()


class TerminateSubAgent(Message):
    """User wants to terminate a running sub-agent."""
    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        super().__init__()


class SetExecutionMode(Message):
    """User wants to change the execution mode."""
    def __init__(self, mode: str) -> None:
        self.mode = mode
        super().__init__()


class RefreshSubAgents(Message):
    """User wants to refresh the sub-agent list."""
    pass


class ShowSubAgentResult(Message):
    """User wants to see a sub-agent's result."""
    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        super().__init__()


class StoreMemoryFact(Message):
    """User wants to store a semantic memory fact."""
    def __init__(self, key: str, content: str) -> None:
        self.key = key
        self.content = content
        super().__init__()


class StoreStrategy(Message):
    """User wants to store a strategic memory."""
    def __init__(self, key: str, content: str, category: str) -> None:
        self.key = key
        self.content = content
        self.category = category
        super().__init__()


# ─── Predefined sub-agent descriptions for the UI ────────────────────────

SUBAGENT_DESCRIPTIONS = {
    "researcher": "🔍 Research — analyze info, search web, read files",
    "coder": "💻 Coder — write, edit, debug code",
    "analyst": "📊 Analyst — query databases, analyze data",
    "reviewer": "🔎 Reviewer — code review, quality checks",
    "writer": "📝 Writer — documentation, content creation",
}

EXECUTION_MODES = {
    "react": "⚡ ReAct — interactive, tool-heavy tasks",
    "plan_and_execute": "📋 Plan & Execute — multi-step with subgoals",
    "hybrid": "🔄 Hybrid — plan first, ReAct per step",
    "auto": "🤖 Auto — let meta-agent decide",
}


# ─── Helper functions for rendering ─────────────────────────────────────────

def format_subagent_status(handle) -> str:
    """Format a sub-agent handle for display in the sidebar."""
    name = handle.name
    status = handle.status.value if hasattr(handle.status, "value") else str(handle.status)
    elapsed = f"{handle.elapsed_ms / 1000:.1f}s" if handle.elapsed_ms else "—"
    mode = handle.config.process_mode.value if hasattr(handle.config, "process_mode") else "?"

    status_emoji = {
        "running": "🟢",
        "completed": "✅",
        "failed": "❌",
        "cancelled": "⏹",
        "timed_out": "⏰",
        "pending": "⏳",
    }.get(status, "❓")

    return f"{status_emoji} {name} ({mode}, {elapsed})"


def format_memory_stats(stats: dict) -> str:
    """Format memory stats for display."""
    vs = stats.get("vector_store", {})
    lines = []
    for collection, count in vs.items():
        name = collection.replace("ltm_", "").title()
        lines.append(f"  {name}: {count} entries")
    return "\n".join(lines) if lines else "  No memory stats available"


# ─── Sidebar Section Compose Helper ──────────────────────────────────────────

def compose_subagents_section() -> Vertical:
    """Compose the sub-agents sidebar section.

    Returns a Vertical container with:
    - Sub-agent type buttons (spawn)
    - Active sub-agents list
    - Execution mode selector
    """
    with Vertical(id="subagents-section"):
        yield Static("[bold]Sub-Agents[/bold]", classes="label")

        # Quick spawn buttons for predefined types
        with Vertical(id="subagent-spawn-buttons"):
            for agent_type, desc in SUBAGENT_DESCRIPTIONS.items():
                yield Button(
                    desc,
                    id=f"spawn-{agent_type}",
                    classes="subagent-spawn-btn",
                )

        # Active sub-agents list
        yield Static("[dim]Active:[/dim]", id="subagents-active-label")
        yield ListView(id="subagents-list", classes="subagents-list")

        # Terminate button
        yield Button("Terminate Selected", id="btn-terminate-subagent", variant="error")

        yield Static("")  # Spacer

    # This will be returned as part of the sidebar


def compose_execution_mode_section() -> Vertical:
    """Compose the execution mode selector section."""
    with Vertical(id="exec-mode-section"):
        yield Static("[bold]Execution Mode[/bold]", classes="label")
        yield Static("react", id="exec-mode-display", classes="value")

        # Mode buttons
        with Vertical(id="exec-mode-buttons"):
            for mode, desc in EXECUTION_MODES.items():
                yield Button(
                    desc,
                    id=f"exec-mode-{mode}",
                    classes="exec-mode-btn",
                )

    # This will be returned as part of the sidebar


def compose_memory_section() -> Vertical:
    """Compose the enhanced memory section with LTM stats."""
    with Vertical(id="memory-ltm-section"):
        yield Static("[bold]Long-Term Memory[/bold]", classes="label")
        yield Static("Loading...", id="ltm-stats-display", classes="value")

        # Memory type counts
        yield Static("[dim]Episodic:[/dim]", id="ltm-episodic-count", classes="value")
        yield Static("[dim]Semantic:[/dim]", id="ltm-semantic-count", classes="value")
        yield Static("[dim]Procedural:[/dim]", id="ltm-procedural-count", classes="value")
        yield Static("[dim]Strategic:[/dim]", id="ltm-strategic-count", classes="value")

    # This will be returned as part of the sidebar


# ─── TUI Action Methods (to be mixed into HolixTUI) ───────────────────────

class SubAgentActions:
    """Mixin class with TUI action methods for sub-agent management.

    To integrate into HolixTUI, add these methods to the HolixTUI class
    and connect the button presses to them in on_button_pressed().
    """

    async def action_spawn_subagent(self, agent_type: str) -> None:
        """Spawn a sub-agent of the given type."""
        if not hasattr(self, '_agent') or not self._agent:
            self._append_to_log("[red]Agent not initialized.[/red]\n")
            return

        # Check if sub-agents are enabled
        from config import settings
        if not settings.enable_subagents:
            self._append_to_log("[yellow]Sub-agents are disabled. Set enable_subagents=True in config.[/yellow]\n")
            return

        from core.subagents.registry import get_subagent_config

        try:
            config = get_subagent_config(agent_type)
        except KeyError:
            self._append_to_log(f"[red]Unknown sub-agent type: {agent_type}[/red]\n")
            return

        # Get task from input area
        input_area = self.query_one("#input-area", TextArea)
        task = input_area.text.strip()
        if not task:
            self._append_to_log("[yellow]Enter a task description in the input field first.[/yellow]\n")
            return

        self._append_to_log(f"[cyan]Spawning {agent_type} sub-agent...[/cyan]\n")
        self._set_status(f"Spawning {agent_type}...", "yellow")

        try:
            await self._agent.subagents.spawn_sub_agent(config, task)
            self._append_to_log(
                f"[green]✓ Sub-agent '{config.name}' spawned "
                f"(mode={config.process_mode.value})[/green]\n"
            )
            self._set_status(f"Running: {config.name}", "green")

            # Refresh the sub-agents list
            await self.action_refresh_subagents()

        except Exception as e:
            self._append_to_log(f"[red]Failed to spawn sub-agent: {e}[/red]\n")
            self._set_status("Error", "red")

    async def action_terminate_subagent(self, agent_name: str) -> None:
        """Terminate a running sub-agent."""
        if not hasattr(self, '_agent') or not self._agent:
            return

        self._append_to_log(f"[yellow]Terminating sub-agent '{agent_name}'...[/yellow]\n")

        try:
            success = await self._agent.subagents.terminate(agent_name)
            if success:
                self._append_to_log(f"[green]✓ Sub-agent '{agent_name}' terminated.[/green]\n")
            else:
                self._append_to_log(f"[yellow]Sub-agent '{agent_name}' not found or already stopped.[/yellow]\n")
        except Exception as e:
            self._append_to_log(f"[red]Error terminating sub-agent: {e}[/red]\n")

        self._set_status("Ready", "green")
        await self.action_refresh_subagents()

    async def action_refresh_subagents(self) -> None:
        """Refresh the sub-agents list in the sidebar."""
        try:
            subagents_list = self.query_one("#subagents-list", ListView)
            await subagents_list.clear()

            if not hasattr(self, '_agent') or not self._agent:
                return

            if not hasattr(self._agent, 'subagents') or not self._agent._subagent_manager:
                return

            handles = self._agent.subagents.list_all()
            for handle in handles:
                status_text = format_subagent_status(handle)
                await subagents_list.append(ListItem(Label(status_text)))

            # Update active count
            active = self._agent.subagents.list_active()
            label = self.query_one("#subagents-active-label", Static)
            await label.update(f"[dim]Active ({len(active)}):[/dim]")

        except Exception:
            pass

    async def action_set_execution_mode(self, mode: str) -> None:
        """Change the execution mode."""
        from config import settings
        settings.execution_mode = mode

        mode_label = {
            "react": "⚡ ReAct",
            "plan_and_execute": "📋 Plan & Execute",
            "hybrid": "🔄 Hybrid",
            "auto": "🤖 Auto",
        }.get(mode, mode)

        self._append_to_log(f"[cyan]Execution mode set to: {mode_label}[/cyan]\n")

        # Update the display
        try:
            display = self.query_one("#exec-mode-display", Static)
            await display.update(mode_label)
        except Exception:
            pass

    async def action_update_ltm_stats(self) -> None:
        """Update the long-term memory stats display."""
        if not hasattr(self, '_agent') or not self._agent:
            return

        if not hasattr(self._agent, 'memory') or not hasattr(self._agent.memory, 'episodic'):
            try:
                display = self.query_one("#ltm-stats-display", Static)
                await display.update("LTM not available")
            except Exception:
                pass
            return

        try:
            stats = self._agent.memory.get_memory_stats()
            vs = stats.get("vector_store", {})

            for collection, count in vs.items():
                name = collection.replace("ltm_", "")
                widget_id = f"ltm-{name}-count"
                try:
                    widget = self.query_one(f"#{widget_id}", Static)
                    await widget.update(f"[dim]{name.title()}:[/dim] {count}")
                except Exception:
                    pass

            total = sum(vs.values())
            display = self.query_one("#ltm-stats-display", Static)
            await display.update(f"[bold]Total: {total} entries[/bold]")

        except Exception:
            try:
                display = self.query_one("#ltm-stats-display", Static)
                await display.update("[dim]Stats unavailable[/dim]")
            except Exception:
                pass

    async def action_store_memory_fact(self, key: str, content: str) -> None:
        """Store a semantic memory fact via TUI."""
        if not hasattr(self, '_agent') or not self._agent:
            return

        if not hasattr(self._agent, 'memory') or not hasattr(self._agent.memory, 'store_fact'):
            self._append_to_log("[yellow]Long-term memory not available.[/yellow]\n")
            return

        try:
            await self._agent.memory.store_fact(key, content, source="tui")
            self._append_to_log(f"[green]✓ Stored fact: {key}[/green]\n")
            await self.action_update_ltm_stats()
        except Exception as e:
            self._append_to_log(f"[red]Failed to store fact: {e}[/red]\n")

    async def action_store_strategy(self, key: str, content: str, category: str = "general") -> None:
        """Store a strategic memory via TUI."""
        if not hasattr(self, '_agent') or not self._agent:
            return

        if not hasattr(self._agent, 'memory') or not hasattr(self._agent.memory, 'store_strategy'):
            self._append_to_log("[yellow]Long-term memory not available.[/yellow]\n")
            return

        try:
            await self._agent.memory.store_strategy(key, content, category=category, source="tui")
            self._append_to_log(f"[green]✓ Stored strategy: {key}[/green]\n")
            await self.action_update_ltm_stats()
        except Exception as e:
            self._append_to_log(f"[red]Failed to store strategy: {e}[/red]\n")


# ─── Slash Commands for TUI Integration ─────────────────────────────────────

SUBAGENT_SLASH_COMMANDS = {
    "/subagent-spawn": "Spawn a sub-agent (type required)",
    "/subagent-list": "List all sub-agents and their status",
    "/subagent-terminate": "Terminate a sub-agent (name required)",
    "/subagent-result": "Show a sub-agent's result (name required)",
    "/subagent-stats": "Show sub-agent manager status summary",
    "/ltm-stats": "Show long-term memory statistics",
    "/ltm-store-fact": "Store a semantic fact (key=value)",
    "/ltm-store-strategy": "Store a strategy (key=value)",
    "/exec-mode": "Set execution mode (react/plan_and_execute/hybrid/auto)",
}

# Need these imports at the bottom to avoid circular issues
try:
    from textual.widgets import Label
except ImportError:
    Label = Static  # Fallback