"""Rich console utilities for beautiful CLI output."""

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.theme import Theme

# Custom theme for Helix
HELIX_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "prompt": "bold bright_cyan",
    "assistant": "bright_white",
    "user": "bright_green",
    "tool": "yellow",
    "dim": "dim",
})

# Global console instance
console = Console(theme=HELIX_THEME)


def print_user_message(message: str):
    """Print user message with styling.

    Args:
        message: User's input message
    """
    console.print(f"\n[user]👤 You:[/user] {message}")


def print_assistant_message(message: str, markdown: bool = True):
    """Print assistant message with Markdown rendering.

    Args:
        message: Assistant's response
        markdown: Whether to render as Markdown
    """
    console.print()
    console.print("[assistant]🤖 Helix:[/assistant]", end=" ")

    if markdown and ("```" in message or "#" in message or "*" in message):
        md = Markdown(message)
        console.print(md)
    else:
        console.print(message, style="assistant")
    console.print()


def print_tool_call(tool_name: str, status: str = "running"):
    """Print tool call indicator.

    Args:
        tool_name: Name of the tool being called
        status: Status (running/done/error)
    """
    if status == "running":
        console.print(f"[tool]🔧 Using tool:[/tool] {tool_name}", style="dim")
    elif status == "done":
        console.print(f"[success]✓[/success] Tool completed: {tool_name}", style="dim")
    elif status == "error":
        console.print(f"[error]✗[/error] Tool failed: {tool_name}", style="dim")


def print_error(message: str):
    """Print error message.

    Args:
        message: Error message
    """
    console.print(f"\n[error]✗ Error:[/error] {message}\n")


def print_success(message: str):
    """Print success message.

    Args:
        message: Success message
    """
    console.print(f"\n[success]✓[/success] {message}\n")


def print_info(message: str):
    """Print info message.

    Args:
        message: Info message
    """
    console.print(f"\n[info]ℹ[/info] {message}\n")


def print_warning(message: str):
    """Print warning message.

    Args:
        message: Warning message
    """
    console.print(f"\n[warning]⚠[/warning] {message}\n")


def create_spinner():
    """Create a spinner progress indicator.

    Returns:
        Progress context manager

    Usage:
        with create_spinner() as progress:
            task = progress.add_task("Loading...", total=None)
            # do work
            progress.update(task, description="Processing...")
    """
    return Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    )


def print_table(title: str, columns: list, rows: list):
    """Print a formatted table.

    Args:
        title: Table title
        columns: List of column names
        rows: List of row data (list of lists)
    """
    table = Table(title=title, box=box.ROUNDED, show_header=True, header_style="bold cyan")

    for col in columns:
        table.add_column(col)

    for row in rows:
        table.add_row(*[str(cell) for cell in row])

    console.print()
    console.print(table)
    console.print()


def print_panel(content: str, title: str = "", border_style: str = "cyan"):
    """Print content in a panel.

    Args:
        content: Panel content
        title: Panel title
        border_style: Border color style
    """
    panel = Panel(content, title=title, border_style=border_style, padding=(1, 2))
    console.print()
    console.print(panel)
    console.print()
