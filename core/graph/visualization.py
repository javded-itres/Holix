"""
Graph Visualization — renders Holix LangGraph execution graphs.

Provides multiple rendering formats:
- ASCII: Simple text representation for terminal display
- Mermaid: Mermaid diagram syntax (can be rendered in Markdown, HTML)
- Rich: Rich library live step-by-step debug view
- Execution trace: Animated rendering of graph execution events
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GraphVisualizer:
    """Visualizes LangGraph execution graphs in multiple formats."""

    # Node type styling for ASCII rendering
    NODE_STYLES = {
        "memory_retrieval": {"icon": "🔍", "label": "Memory Retrieval"},
        "react": {"icon": "🧠", "label": "ReAct Reasoning"},
        "tool_execution": {"icon": "🔧", "label": "Tool Execution"},
        "finalize": {"icon": "✅", "label": "Finalize"},
        "plan": {"icon": "📋", "label": "Plan Generation"},
        "execute_step": {"icon": "⚡", "label": "Execute Step"},
        "meta_agent": {"icon": "🎯", "label": "Meta-Agent"},
        "self_refinement": {"icon": "🔄", "label": "Self-Refinement"},
        "sub_agent_dispatch": {"icon": "🤖", "label": "Sub-Agent Dispatch"},
        "synthesis": {"icon": "🔗", "label": "Synthesis"},
    }

    # Edge labels for conditional routing
    EDGE_LABELS = {
        "tools": "has tool_calls",
        "final": "is_final=True",
        "max_steps": "max_steps reached",
        "next_step": "next plan step",
        "needs_refinement": "needs refinement",
    }

    def render_ascii(self, graph_description: str | None = None) -> str:
        """Render the default Holix graph as ASCII art.

        Args:
            graph_description: Optional description to include in the output.
                             If None, renders the default ReAct graph.

        Returns:
            ASCII representation of the graph.
        """
        lines = []
        lines.append("╔══════════════════════════════════════╗")
        lines.append("║       Holix Agent Execution Graph     ║")
        lines.append("╚══════════════════════════════════════╝")
        lines.append("")
        lines.append("  ┌─────────┐")
        lines.append("  │  START   │")
        lines.append("  └────┬─────┘")
        lines.append("       │")
        lines.append("       ▼")
        lines.append("  ┌──────────────────┐")
        lines.append("  │ 🔍 Memory         │")
        lines.append("  │    Retrieval      │")
        lines.append("  └────────┬─────────┘")
        lines.append("           │")
        lines.append("           ▼")
        lines.append("  ┌──────────────────┐")
        lines.append("  │ 🧠 ReAct          │")
        lines.append("  │    Reasoning      │")
        lines.append("  └────────┬─────────┘")
        lines.append("           │")
        lines.append("     ┌─────┴─────┐")
        lines.append("     │  Route?   │")
        lines.append("     └──┬─────┬──┘")
        lines.append("        │     │")
        lines.append("   tools     is_final/max_steps")
        lines.append("        │     │")
        lines.append("        ▼     ▼")
        lines.append("  ┌─────────┐ ┌──────────┐")
        lines.append("  │ 🔧 Tool  │ │ ✅ Final- │")
        lines.append("  │  Exec    │ │    ize   │")
        lines.append("  └────┬────┘ └────┬─────┘")
        lines.append("       │           │")
        lines.append("       │           ▼")
        lines.append("       │        ┌──────┐")
        lines.append("       │        │ END  │")
        lines.append("       │        └──────┘")
        lines.append("       │")
        lines.append("       └──────► back to 🧠 ReAct")
        lines.append("")

        if graph_description:
            lines.append(f"  Description: {graph_description}")
            lines.append("")

        return "\n".join(lines)

    def render_mermaid(self, graph_type: str = "react") -> str:
        """Render the graph as a Mermaid diagram.

        Args:
            graph_type: Type of graph to render.
                       "react", "plan_and_execute", or "hybrid".

        Returns:
            Mermaid diagram syntax string.
        """
        if graph_type == "plan_and_execute":
            return self._render_plan_execute_mermaid()
        elif graph_type == "hybrid":
            return self._render_hybrid_mermaid()
        else:
            return self._render_react_mermaid()

    def _render_react_mermaid(self) -> str:
        """Render the ReAct graph as Mermaid."""
        return """graph TD
    START((START)) --> MR[🔍 Memory Retrieval]
    MR --> REACT[🧠 ReAct Reasoning]
    REACT --> ROUTE{Route?}
    ROUTE -->|has tool_calls| TOOLS[🔧 Tool Execution]
    ROUTE -->|is_final=True| FINAL[✅ Finalize]
    ROUTE -->|max_steps reached| FINAL
    TOOLS --> REACT
    FINAL --> END((END))

    style MR fill:#e1f5fe
    style REACT fill:#fff3e0
    style TOOLS fill:#e8f5e9
    style FINAL fill:#fce4ec
    style ROUTE fill:#f3e5f5"""

    def _render_plan_execute_mermaid(self) -> str:
        """Render the Plan-and-Execute graph as Mermaid."""
        return """graph TD
    START((START)) --> MR[🔍 Memory Retrieval]
    MR --> PLAN[📋 Plan Generation]
    PLAN --> EXEC[⚡ Execute Step]
    EXEC --> ROUTE{More steps?}
    ROUTE -->|yes| EXEC
    ROUTE -->|no| FINAL[✅ Finalize]
    FINAL --> END((END))

    style MR fill:#e1f5fe
    style PLAN fill:#f3e5f5
    style EXEC fill:#fff3e0
    style FINAL fill:#fce4ec"""

    def _render_hybrid_mermaid(self) -> str:
        """Render the Hybrid graph as Mermaid."""
        return """graph TD
    START((START)) --> MR[🔍 Memory Retrieval]
    MR --> PLAN[📋 Plan Generation]
    PLAN --> REACT[🧠 ReAct per Step]
    REACT --> ROUTE{Route?}
    ROUTE -->|has tool_calls| TOOLS[🔧 Tool Execution]
    ROUTE -->|is_final step| NEXT{Next step?}
    NEXT -->|yes| REACT
    NEXT -->|no, all done| FINAL[✅ Finalize]
    TOOLS --> REACT
    FINAL --> END((END))

    style MR fill:#e1f5fe
    style PLAN fill:#f3e5f5
    style REACT fill:#fff3e0
    style TOOLS fill:#e8f5e9
    style FINAL fill:#fce4ec"""

    def render_rich(self, graph_type: str = "react") -> str:
        """Render the graph using Rich console markup.

        Args:
            graph_type: Type of graph to render.

        Returns:
            Rich-formatted string with colors and styles.
        """
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.table import Table
            console = Console(width=80, force_terminal=True)

            # Create a table of nodes
            table = Table(title="Holix Graph Nodes", show_header=True)
            table.add_column("Node", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Description", style="white")

            node_descriptions = {
                "memory_retrieval": "Queries all 4 LTM stores in parallel",
                "react": "LLM reasoning + tool calls loop",
                "tool_execution": "Executes pending tool calls",
                "finalize": "Saves response, triggers self-improvement",
                "plan": "Decomposes task into ordered sub-steps",
                "execute_step": "Executes next step via ReAct sub-loop",
            }

            for node_key, info in self.NODE_STYLES.items():
                if node_key in node_descriptions:
                    table.add_row(
                        f"{info['icon']} {info['label']}",
                        node_key,
                        node_descriptions[node_key],
                    )

            console.print(table)

            # Render edges
            mermaid = self.render_mermaid(graph_type)
            console.print(Panel(mermaid, title="Mermaid Diagram", border_style="blue"))

            # Capture output
            from io import StringIO
            sio = StringIO()
            console = Console(file=sio, width=80, force_terminal=False)
            console.print(table)
            console.print(Panel(mermaid, title="Mermaid Diagram", border_style="blue"))

            return sio.getvalue()

        except ImportError:
            # Rich not available, fall back to ASCII
            return self.render_ascii(graph_type)

    def render_graph_execution(
        self,
        events: list[dict[str, Any]],
        graph_type: str = "react",
    ) -> str:
        """Render an execution trace of graph events.

        Args:
            events: List of event dicts from the graph execution.
            graph_type: Type of graph.

        Returns:
            Formatted execution trace string.
        """
        lines = []
        lines.append("═" * 50)
        lines.append(f"  Holix Graph Execution Trace ({graph_type})")
        lines.append("═" * 50)
        lines.append("")

        step = 0
        for event in events:
            event_type = event.get("type", "unknown")
            step += 1

            if event_type == "node_start":
                node = event.get("node", "unknown")
                style = self.NODE_STYLES.get(node, {"icon": "●", "label": node})
                lines.append(f"  Step {step}: {style['icon']} Enter {style['label']}")
                if event.get("input"):
                    input_str = str(event["input"])[:60]
                    lines.append(f"           Input: {input_str}...")

            elif event_type == "node_end":
                node = event.get("node", "unknown")
                style = self.NODE_STYLES.get(node, {"icon": "●", "label": node})
                lines.append(f"  Step {step}: ✅ Exit {style['label']}")
                if event.get("output"):
                    output_str = str(event["output"])[:60]
                    lines.append(f"           Output: {output_str}...")

            elif event_type == "conditional_route":
                condition = event.get("condition", "unknown")
                target = event.get("target", "unknown")
                label = self.EDGE_LABELS.get(condition, condition)
                lines.append(f"  Step {step}: ↪ Route: {label} → {target}")

            elif event_type == "error":
                error = event.get("error", "unknown error")
                lines.append(f"  Step {step}: ❌ Error: {error[:80]}")

        lines.append("")
        lines.append("═" * 50)
        lines.append(f"  Total steps: {step}")
        lines.append("═" * 50)

        return "\n".join(lines)

    def get_available_graphs(self) -> list[dict[str, str]]:
        """List available graph types and their descriptions.

        Returns:
            List of dicts with graph_type, name, and description.
        """
        return [
            {
                "graph_type": "react",
                "name": "ReAct",
                "description": "Interactive reasoning with tool calls. Best for exploratory tasks.",
            },
            {
                "graph_type": "plan_and_execute",
                "name": "Plan & Execute",
                "description": "Decompose task into plan, then execute each step. Best for multi-step tasks.",
            },
            {
                "graph_type": "hybrid",
                "name": "Hybrid",
                "description": "Plan first, then execute each step with ReAct. Best for complex tasks.",
            },
        ]