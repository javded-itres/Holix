"""Beautiful ASCII art banner for Helix CLI."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

HELIX_BANNER = """
██╗  ██╗███████╗██╗     ██╗██╗  ██╗
██║  ██║██╔════╝██║     ██║╚██╗██╔╝
███████║█████╗  ██║     ██║ ╚███╔╝
██╔══██║██╔══╝  ██║     ██║ ██╔██╗
██║  ██║███████╗███████╗██║██╔╝ ██╗
╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝  ╚═╝
"""

def show_banner(console: Console, profile: str = "default"):
    """Display the Helix welcome banner.

    Args:
        console: Rich console instance
        profile: Active profile name
    """
    banner_text = Text(HELIX_BANNER, style="bold cyan")

    subtitle = Text()
    subtitle.append("Self-Improving AI Agent", style="italic bright_white")
    subtitle.append(" • ", style="dim")
    subtitle.append(f"Profile: {profile}", style="bold yellow")
    subtitle.append(" • ", style="dim")
    subtitle.append("v0.1.0", style="dim")

    panel = Panel(
        banner_text + "\n" + subtitle,
        border_style="cyan",
        padding=(1, 2)
    )

    console.print(panel)
    console.print()


def show_welcome_message(console: Console):
    """Show welcome message with helpful commands.

    Args:
        console: Rich console instance
    """
    console.print("Welcome to Helix! 🚀\n", style="bold green")
    console.print("Special commands:", style="cyan")
    console.print("  /clear            - Clear current conversation", style="dim")
    console.print("  /model            - Switch LLM model", style="dim")
    console.print("  /profile          - Switch profile", style="dim")
    console.print("  /skills           - Show active skills", style="dim")
    console.print("  /memory           - Search memory", style="dim")
    console.print("  /metrics          - Show agent metrics", style="dim")
    console.print("  /stream           - Toggle streaming mode", style="dim")
    console.print("  /debug events [N] - Show recent events", style="dim")
    console.print("  /help             - Show all commands", style="dim")
    console.print("  /exit             - Exit chat\n", style="dim")
