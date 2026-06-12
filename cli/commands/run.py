"""Single query execution command."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from core.di import create_agent, resolve_runtime_config

from cli.core import ProfileConfig
from cli.utils.rich_console import (
    create_spinner,
    print_assistant_message,
    print_error,
    print_user_message,
)


async def run_single_query(query: str, conversation_id: str, config: ProfileConfig):
    """Execute a single query and exit.

    Args:
        query: Query to execute
        conversation_id: Conversation ID
        config: Profile configuration
    """
    runtime_config = resolve_runtime_config(config)

    with create_spinner() as progress:
        task = progress.add_task("Initializing Holix...", total=None)
        from core.agent_events import create_compatibility_print_handler, create_rich_cli_handler
        try:
            handler = create_rich_cli_handler()
        except Exception:
            handler = create_compatibility_print_handler()

        container = None
        try:
            agent, container = await create_agent(
                runtime_config,
                event_listeners=[handler],
            )
        finally:
            progress.remove_task(task)

    print_user_message(query)

    with create_spinner() as progress:
        task = progress.add_task("Holix is thinking...", total=None)
        try:
            response = await agent.run(user_input=query, conversation_id=conversation_id)
        except Exception as e:
            progress.remove_task(task)
            print_error(f"Error: {e}")
            return
        finally:
            if task in progress.task_ids:
                progress.remove_task(task)

    print_assistant_message(response, markdown=True)

    if container is not None:
        await container.close()