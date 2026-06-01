"""Memory management commands."""

import typer
import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))

from cli.utils.rich_console import print_table, print_info, print_error, console

app = typer.Typer(help="Search and manage Helix memory")


@app.command("search")
def search_memory(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(10, "--limit", "-l", help="Number of results")
):
    """Search through agent memory."""
    config = ctx.obj["config"]

    # Run async search
    asyncio.run(_search_memory_async(query, top_k, config))


async def _search_memory_async(query: str, top_k: int, config):
    """Async memory search."""
    from core.memory.manager import MemoryManager

    # Update global config
    import config as global_config
    global_config.settings.memory_db_path = config.memory_db_path
    global_config.settings.vector_db_path = config.vector_db_path

    manager = MemoryManager()
    await manager.initialize_db()

    results = await manager.search(query, top_k=top_k)

    if results:
        console.print(f"\n[cyan]Found {len(results)} results:[/cyan]\n")
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            metadata = result.get("metadata", {})

            console.print(f"[bold]{i}.[/bold] {content[:200]}...")
            if metadata:
                console.print(f"   [dim]Conversation: {metadata.get('conversation_id', 'N/A')}[/dim]")
            console.print()
    else:
        print_info("No results found")
